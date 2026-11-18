(ns review-queue.main
  "Reads the review queue, fetches each GitHub item's state and stacks with
  `gh`, and prints the chunks and the finished items, in the queue's
  format. It then sets the named Google Chrome tab group to the current
  chunk's URLs through `declarative-tab-groups`, which never focuses a
  window or a review tab. With `--announce`, it first tells the user what
  will load and waits 1 second, and with `--notify` it tells the user once
  the group is set."
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
   :group {:default "Review" :desc "The title of the tab group the review items open in"}
   :sound {:default "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Handoff-EncoreInfinitum.caf"
           :desc "The sound the Review ready notification plays"}
   :announce-sound {:default "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Slide-EncoreInfinitum.caf"
                    :desc "The sound the notice before the group is set plays"}
   :announce {:coerce :boolean :desc "Before setting the group: say what will load, play --announce-sound, wait 1 s"}
   :notify {:coerce :boolean :desc "Once the group is set: play --sound and show the Review ready notification"}
   :help {:coerce :boolean :alias :h}})

(def ^:private command "declarative-tab-groups")

(def ^:private install
  (str "Install it, with its Google Chrome extension, as the README of "
       "https://github.com/nhooey/chrome-extension-declarative-tab-groups says."))

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

(defn- applescript-string [s]
  (str "\"" (-> s (str/replace "\\" "\\\\") (str/replace "\"" "\\\"")) "\""))

(defn notify!
  "Plays `sound` while showing `note`, through terminal-notifier in the
  note's group, else osascript. Through terminal-notifier, it then checks
  with `-list` that the notification was delivered. `env` holds `:run`,
  which runs a command vector and returns its `:exit`, `:out` and `:err`,
  `:spawn`, which starts one without waiting, `:which` and `:sleep`."
  [{:keys [title message url] group-id :group} sound {:keys [run spawn which]}]
  (spawn ["afplay" sound])
  (if (which "terminal-notifier")
    (do (run (cond-> ["terminal-notifier" "-title" title "-message" message "-group" group-id]
               url (into ["-open" url])))
        {:delivered (group/delivered? group-id (:out (run ["terminal-notifier" "-list" group-id])))})
    (do (run ["osascript" "-e" (str "display notification " (applescript-string message)
                                    " with title " (applescript-string title))])
        {})))

(defn announce!
  "Shows `note`, what is about to load, with `sound`, then waits 1 second
  so the user is ready before anything moves."
  [note sound {:keys [sleep] :as env}]
  (let [result (notify! note sound env)]
    (sleep 1000)
    result))

(defn response
  "What a run of `declarative-tab-groups set --json` means, from its
  `:exit`, `:out` and `:err`: `:tab-group`, the success response, whose
  `:kept` tabs stay open for their unsubmitted forms, or a `:failure`
  message."
  [{:keys [exit out err]}]
  (let [answer (try (json/parse-string out true) (catch Exception _ nil))
        {:keys [code message]} (when (map? answer) (:error answer))
        said (if code (str code ": " message) (str/trim (str err)))]
    (cond
      (= exit 4) {:failure (str command " can't reach Google Chrome's extension (" said
                                "); start Google Chrome with the extension. " install)}
      (= exit 2) {:failure (str command " refused its arguments: " said)}
      (not (map? answer)) {:failure (str command " exited " exit " without a JSON response: "
                                         (str/trim (str out)))}
      (and (#{0 3} exit) (true? (:ok answer))) {:tab-group (dissoc answer :protocol :ok :command)}
      :else {:failure (str command " failed: " said)})))

(defn set-group!
  "Makes the tab group titled `title` hold exactly `urls`, in order, each
  loaded afresh, through declarative-tab-groups, and returns its
  `response`. The URLs follow `--`, so none is taken for an option."
  [title urls {:keys [run]}]
  (response (run (into [command "set" "--group" title "--json" "--"] urls))))

(defn reconcile!
  "Sets the group titled `(:group opts)` to the URLs of `items`: with
  `:announce`, says first what will load, and with `:notify`, tells the
  user once it is set. Returns `:tab-group` or `:failure`, with the
  `:announcement` and `:notification` sent. A missing command is a
  failure, before anything is announced."
  [opts items {:keys [which] :as env}]
  (if-not (which command)
    {:failure (str command " isn't on the PATH. " install)}
    (let [urls (group/urls items)
          note (when (:announce opts) (group/announcement (:group opts) urls))
          announced (when note (merge note (announce! note (:announce-sound opts) env)))
          result (set-group! (:group opts) urls env)
          ready (when (and (:notify opts) (:tab-group result)) (group/notification items))
          told (when ready (merge ready (notify! ready (:sound opts) env)))]
      (cond-> result
        announced (assoc :announcement announced)
        told (assoc :notification told)))))

(defn- parse [format text]
  (if (= format :json) (json/parse-string text true) (edn/read-string text)))

(defn- render [format data]
  (if (= format :json)
    (println (json/generate-string data {:pretty true}))
    (pprint/pprint data)))

(defn- warn [message]
  (binding [*out* *err*] (println (str "review-queue: " message))))

(defn- warn-undelivered [what {:keys [delivered]}]
  (when (false? delivered)
    (warn (str "the " what " notification wasn't delivered"))))

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
            result (reconcile! opts (group/group-items plan (:chunk-mode opts)) system)]
        (warn-undelivered "announcement" (:announcement result))
        (warn-undelivered "Review ready" (:notification result))
        (doseq [{:keys [url title]} (get-in result [:tab-group :kept])]
          (warn (str "left open for its unsubmitted form: " title " " url)))
        (some-> (:failure result) warn)
        (render format (merge plan result))
        (when (:failure result) (System/exit 1))))))

(defn options
  "The options `args` give, with each one's default."
  [args]
  (:opts (cli/parse-args args {:spec spec})))

(defn -main [& args]
  (let [{:keys [opts args]} (cli/parse-args args {:spec spec})]
    (if (:help opts)
      (println (str "Usage: review-queue [options] [QUEUE-FILE]\n"
                    "Reads the queue from QUEUE-FILE, or stdin.\n\n"
                    (cli/format-opts {:spec spec})))
      (review opts (first args)))))
