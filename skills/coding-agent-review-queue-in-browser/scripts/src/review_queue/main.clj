(ns review-queue.main
  "Reads the review queue, fetches each GitHub item's state and stacks with
  `gh`, and prints the chunks and the finished items, in the queue's
  format. With `--announce`, it first tells the user what the reconcile
  will do and waits 1 second. Given the tab group's tabs, it adds the
  `:tab-actions` that bring the group to its end state, with
  `--apply-window` parks the window on a new tab and re-points tabs in the
  background, and with `--notify` sends the notification. With
  `--focus-window`, it only makes the focus tab its window's active tab
  and closes the `--unpark` tab, never raising the window or the app."
  (:require [babashka.cli :as cli]
            [babashka.fs :as fs]
            [babashka.process :as p]
            [cheshire.core :as json]
            [clojure.edn :as edn]
            [clojure.pprint :as pprint]
            [clojure.string :as str]
            [review-queue.core :as core]
            [review-queue.group :as group]))

(def ^:private spec
  {:chunk-size {:coerce :long :default 5 :desc "Most items in a chunk"}
   :format {:coerce :keyword :desc "edn or json; default from the file's extension, else edn"}
   :no-fetch {:coerce :boolean :desc "Don't ask gh for states and stacks"}
   :chunk-mode {:coerce :keyword :default :current-only :desc "current-only or all-open"}
   :app {:default "Google Chrome" :desc "The browser app"}
   :sound {:default "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Handoff-EncoreInfinitum.caf"
           :desc "The sound the Review ready notification plays"}
   :announce-sound {:default "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Slide-EncoreInfinitum.caf"
                    :desc "The sound the notice before a reconcile plays"}
   :announce {:coerce :boolean :desc "Before a reconcile: show the steps it will take, play --announce-sound, wait 1 s"}
   :launch {:coerce :boolean :desc "With --announce, the browser check will launch --app"}
   :open-window {:coerce :boolean :desc "With --announce, the browser check will open a new window"}
   :tabs {:desc "The tab group's tabs, in its order, as a JSON list of {tabId, url, untouchable}"}
   :notify {:coerce :boolean :desc "With --tabs, play --sound and show the :notification, if any"}
   :apply-window {:coerce :long :desc "With --tabs, park on a new tab and re-point tabs in the background in this window id, from the browser check"}
   :focus-window {:coerce :long :desc "Only make --focus-url's tab active in this window id, from the browser check, and close --unpark's tab"}
   :focus-url {:desc "With --focus-window, the URL of the tab to make active"}
   :unpark {:coerce :long :desc "With --focus-window, the parking tab's id, :parked in --apply-window's :tab-actions"}
   :help {:coerce :boolean :alias :h}})

(defn- gh-state [{:keys [type url]}]
  (let [{:keys [exit out err]} (p/shell {:out :string :err :string :continue true}
                                        "gh" (if (= type :pr) "pr" "issue") "view" url
                                        "--json" "state" "--jq" ".state")]
    (if (zero? exit) {:state (str/trim out)} {:state-error (str/trim err)})))

(defn- with-state [item]
  (if-let [ref (and (not (:done item)) (core/github-ref (:url item)))]
    (merge item (gh-state ref))
    item))

(defn- open-prs
  "Every open pull request of `repo` (`github.com/owner/name`), with its
  base and head branches, for finding stacks."
  [repo]
  (let [{:keys [exit out]} (p/shell {:out :string :err :string :continue true}
                                    "gh" "pr" "list" "--repo" repo "--state" "open" "--limit" "500"
                                    "--json" "url,baseRefName,headRefName")]
    (if (zero? exit)
      (mapv (fn [{:keys [url baseRefName headRefName]}] {:url url :base baseRefName :head headRefName})
            (json/parse-string out true))
      [])))

(def ^:private system
  {:run #(apply p/shell {:continue true :out :string :err :string} %)
   :spawn #(apply p/process %)
   :which #(some? (fs/which %))
   :sleep #(Thread/sleep (long %))})

(defn notify!
  "Plays `sound` while showing `note`, through terminal-notifier in the
  note's group, else osascript. Through terminal-notifier, it then checks
  with `-list` that the notification was delivered. `env` holds `:run`,
  which runs a command vector and returns its `:out`, `:spawn`, which
  starts one without waiting, and `:which`."
  [{:keys [title message url] group-id :group} sound {:keys [run spawn which]}]
  (spawn ["afplay" sound])
  (if (which "terminal-notifier")
    (do (run (cond-> ["terminal-notifier" "-title" title "-message" message "-group" group-id]
               url (into ["-open" url])))
        {:delivered (group/delivered? group-id (:out (run ["terminal-notifier" "-list" group-id])))})
    (do (run ["osascript" "-e" (str "display notification " (group/applescript-string message)
                                    " with title " (group/applescript-string title))])
        {})))

(defn announce!
  "Shows `note`, the steps a reconcile will take, with `sound`, then waits
  1 second so the user is ready before anything moves."
  [note sound {:keys [sleep] :as env}]
  (let [result (notify! note sound env)]
    (sleep 1000)
    result))

(defn apply!
  "Starts the update in `app`'s window `window-id` through AppleScript:
  parks the window on a new tab, with `:park`, then re-points the
  `actions`' tabs in the background. Returns whether it ran anything, and
  the parking tab's id as `:parked`."
  [app window-id actions {:keys [run]}]
  (if-let [script (group/background-script app window-id actions)]
    (let [{:keys [out]} (run ["osascript" "-e" script])]
      (cond-> {:applied true}
        (:park actions) (assoc :parked (some-> out str/trim parse-long))))
    {:applied false}))

(defn focus!
  "Lands the update: makes the tab showing `url` the active tab of `app`'s
  window `window-id`, then closes the `parked` tab, if any, without raising
  the window or the app."
  [app window-id url parked {:keys [run]}]
  (run ["osascript" "-e" (group/focus-script app window-id url parked)]))

(defn- parse [format text]
  (if (= format :json) (json/parse-string text true) (edn/read-string text)))

(defn- render [format data]
  (if (= format :json)
    (println (json/generate-string data {:pretty true}))
    (pprint/pprint data)))

(defn- warn-undelivered [what {:keys [delivered]}]
  (when (false? delivered)
    (binding [*out* *err*] (println (str "review-queue: the " what " notification wasn't delivered")))))

(defn- review [opts file]
  (let [format (or (:format opts) (if (some-> file (str/ends-with? ".json")) :json :edn))
        items (core/normalize (parse format (if file (slurp file) (slurp *in*))))
        problems (core/problems items)]
    (if (seq problems)
      (do (run! #(binding [*out* *err*] (println %)) problems)
          (System/exit 2))
      (let [plan (core/plan (:chunk-size opts)
                            (if (:no-fetch opts)
                              items
                              (core/with-stacks (vec (pmap with-state items))
                                (vec (mapcat open-prs (core/pr-repos items))))))
            tabs (some-> (:tabs opts) (json/parse-string true))
            actions (group/for-plan plan (:chunk-mode opts) (or tabs []))
            note (when (:announce opts) (group/announcement (:app opts) opts actions))
            announced (when note (merge note (announce! note (:announce-sound opts) system)))
            actions (when tabs
                      (cond-> actions
                        (:apply-window opts)
                        (merge (apply! (:app opts) (:apply-window opts) actions system))))
            told (when (and (:notify opts) (:notification actions))
                   (merge (:notification actions) (notify! (:notification actions) (:sound opts) system)))]
        (warn-undelivered "announcement" announced)
        (warn-undelivered "Review ready" told)
        (render format (cond-> plan
                         announced (assoc :announcement announced)
                         actions (assoc :tab-actions (cond-> actions told (assoc :notification told)))))))))

(defn options
  "The options `args` give, with each one's default."
  [args]
  (:opts (cli/parse-args args {:spec spec})))

(defn -main [& args]
  (let [{:keys [opts args]} (cli/parse-args args {:spec spec})]
    (cond
      (:help opts)
      (println (str "Usage: review-queue [options] [QUEUE-FILE]\n"
                    "Reads the queue from QUEUE-FILE, or stdin.\n\n"
                    (cli/format-opts {:spec spec})))
      (:focus-window opts)
      (focus! (:app opts) (:focus-window opts) (:focus-url opts) (:unpark opts) system)
      :else
      (review opts (first args)))))
