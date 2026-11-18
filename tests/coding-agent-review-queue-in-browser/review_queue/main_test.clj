(ns review-queue.main-test
  (:require [cheshire.core :as json]
            [clojure.string :as str]
            [clojure.test :refer [deftest is testing]]
            [review-queue.group :as group]
            [review-queue.main :as main]))

(def ^:private pr "https://github.com/o/r/pull/1")
(def ^:private pr2 "https://github.com/o/r/pull/2")
(def ^:private report "https://github.com/o/r/issues/3")

(def ^:private header "GroupID\tTitle\tSubtitle\tMessage\tDelivered At")

(def ^:private set-ok
  {:exit 0
   :out (json/generate-string {:protocol 1 :ok true :command "set"
                               :group {:title "Review" :windowId 7 :created false}
                               :opened 2 :closed 1 :kept [] :unchecked 0 :loading 0})})

(defn- recorded
  "Stubs of afplay, terminal-notifier, osascript and declarative-tab-groups:
  `found` names the commands on the path, `listed` is what
  `terminal-notifier -list` prints, and `answer` is what
  declarative-tab-groups exits with and prints. Every call lands in the
  returned atom, tagged by how it ran."
  ([found listed] (recorded found listed set-ok))
  ([found listed answer]
   (let [calls (atom [])]
     [calls {:run (fn [cmd] (swap! calls conj [:run cmd])
                    (cond
                      (= "declarative-tab-groups" (first cmd)) answer
                      (= "-list" (second cmd)) {:exit 0 :out listed}
                      :else {:exit 0 :out ""}))
             :spawn (fn [cmd] (swap! calls conj [:spawn cmd]))
             :which #(contains? found %)
             :sleep (fn [ms] (swap! calls conj [:sleep ms]))}])))

(def ^:private note {:title "Review ready" :message "1 to review: say \"hi\"" :url pr :group "review"})

(deftest notify
  (testing "the sound starts without waiting, terminal-notifier shows the notification, and -list checks it"
    (let [[calls env] (recorded #{"terminal-notifier"} (str header "\nreview\tReview ready\t\tx\t2026"))]
      (is (= {:delivered true} (main/notify! note "/x/Handoff.caf" env)))
      (is (= [[:spawn ["afplay" "/x/Handoff.caf"]]
              [:run ["terminal-notifier" "-title" "Review ready" "-message" "1 to review: say \"hi\""
                     "-group" "review" "-open" pr]]
              [:run ["terminal-notifier" "-list" "review"]]]
             @calls))))
  (testing "a notification -list doesn't show isn't delivered"
    (let [[_ env] (recorded #{"terminal-notifier"} header)]
      (is (= {:delivered false} (main/notify! note "/x/Handoff.caf" env)))))
  (testing "without terminal-notifier, osascript shows it, quoted, unchecked"
    (let [[calls env] (recorded #{} "")]
      (is (= {} (main/notify! note "/x/Handoff.caf" env)))
      (is (= [:run ["osascript" "-e"
                    "display notification \"1 to review: say \\\"hi\\\"\" with title \"Review ready\""]]
             (second @calls))))))

(deftest announce
  (testing "what will load shows with the sound in its own group, then it waits 1 second"
    (let [[calls env] (recorded #{"terminal-notifier"} (str header "\nreview-start\tReview queue\t\tx\t2026"))
          steps (group/announcement "Review" [pr pr2 report])]
      (is (= {:delivered true} (main/announce! steps "/x/Handoff.caf" env)))
      (is (= [[:spawn ["afplay" "/x/Handoff.caf"]]
              [:run ["terminal-notifier" "-title" "Review queue" "-message" (:message steps)
                     "-group" "review-start"]]
              [:run ["terminal-notifier" "-list" "review-start"]]
              [:sleep 1000]]
             @calls)))))

(deftest sounds
  (testing "the notice before a reconcile plays Slide, and Review ready plays Handoff, each its own option"
    (is (= {:announce-sound "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Slide-EncoreInfinitum.caf"
            :sound "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Handoff-EncoreInfinitum.caf"}
           (select-keys (main/options []) [:announce-sound :sound])))
    (is (= "/x/Other.caf" (:announce-sound (main/options ["--announce-sound" "/x/Other.caf"]))))))

(defn- item [url kind] {:url url :kind kind :topic "t"})

(defn- programs
  "Each call's tag and program, or a sleep's milliseconds."
  [calls]
  (mapv (fn [[how x]] [how (if (vector? x) (first x) x)]) calls))

(deftest set-group
  (testing "one set of the Review group, the URLs on their Overview after --, so none is taken for an option"
    (let [[calls env] (recorded #{"declarative-tab-groups"} "")]
      (main/reconcile! (main/options []) [(item pr :merge) (item (str pr2 "/files") :merge)
                                          (item report :report)] env)
      (is (= [[:run ["declarative-tab-groups" "set" "--group" "Review" "--json" "--" pr pr2 report]]]
             @calls))))
  (testing "an empty queue still sets the group, with no URL, so it keeps only its status page"
    (let [[calls env] (recorded #{"declarative-tab-groups"} "")]
      (main/reconcile! (main/options []) [] env)
      (is (= [[:run ["declarative-tab-groups" "set" "--group" "Review" "--json" "--"]]] @calls))))
  (testing "the preferences' title names the group"
    (let [[calls env] (recorded #{"declarative-tab-groups"} "")]
      (main/reconcile! (main/options ["--group" "Mine to review"]) [(item pr :merge)] env)
      (is (= [[:run ["declarative-tab-groups" "set" "--group" "Mine to review" "--json" "--" pr]]]
             @calls))))
  (testing "--announce tells the user before the group is set, and --notify after"
    (let [[calls env] (recorded #{"declarative-tab-groups" "terminal-notifier"} "")
          result (main/reconcile! (main/options ["--announce" "--notify"]) [(item pr :merge)] env)]
      (is (= [[:spawn "afplay"] [:run "terminal-notifier"] [:run "terminal-notifier"] [:sleep 1000]
              [:run "declarative-tab-groups"]
              [:spawn "afplay"] [:run "terminal-notifier"] [:run "terminal-notifier"]]
             (programs @calls)))
      (is (= "Review queue" (get-in result [:announcement :title])))
      (is (= "Review ready" (get-in result [:notification :title])))))
  (testing "a failed set tells no one the group is ready"
    (let [[calls env] (recorded #{"declarative-tab-groups" "terminal-notifier"} ""
                                {:exit 4 :out "" :err ""})
          result (main/reconcile! (main/options ["--notify"]) [(item pr :merge)] env)]
      (is (contains? result :failure))
      (is (nil? (:notification result)))
      (is (= [[:run "declarative-tab-groups"]] (programs @calls))))))

(def ^:private readme "https://github.com/nhooey/chrome-extension-declarative-tab-groups")

(defn- failed [code message]
  (json/generate-string {:protocol 1 :ok false :error {:code code :message message}}))

(deftest responses
  (testing "exit 0: the group, as the command reports it"
    (is (= {:tab-group {:group {:title "Review" :windowId 7 :created false}
                        :opened 2 :closed 1 :kept [] :unchecked 0 :loading 0}}
           (main/response set-ok))))
  (testing "exit 3 is no failure: the kept tabs, by URL and title, stay open for their forms"
    (let [kept [{:url "https://github.com/o/r/issues/new" :title "New issue"}]
          result (main/response {:exit 3 :out (json/generate-string
                                               (assoc (json/parse-string (:out set-ok) true) :kept kept))})]
      (is (nil? (:failure result)))
      (is (= kept (get-in result [:tab-group :kept])))))
  (testing "exit 4: not connected, naming the install step"
    (let [{:keys [failure tab-group]} (main/response {:exit 4 :out (failed "not-connected" "no host listens")})]
      (is (nil? tab-group))
      (is (str/includes? failure "not-connected: no host listens"))
      (is (str/includes? failure readme))))
  (testing "exit 1: the response's error code and message"
    (is (= {:failure "declarative-tab-groups failed: no-window: no Chrome window can hold the group"}
           (main/response {:exit 1 :out (failed "no-window" "no Chrome window can hold the group")
                           :err "declarative-tab-groups: no-window: no Chrome window can hold the group\n"}))))
  (testing "exit 2: the usage error the command printed"
    (is (= {:failure "declarative-tab-groups refused its arguments: declarative-tab-groups: unknown option --x"}
           (main/response {:exit 2 :out "" :err "declarative-tab-groups: unknown option --x\n"}))))
  (testing "output that isn't JSON is a failure"
    (is (= {:failure "declarative-tab-groups exited 0 without a JSON response: opened 2"}
           (main/response {:exit 0 :out "opened 2\n"}))))
  (testing "the command missing from the PATH: nothing runs, and the install step is named"
    (let [[calls env] (recorded #{"terminal-notifier"} "")
          {:keys [failure]} (main/reconcile! (main/options ["--announce" "--notify"]) [(item pr :merge)] env)]
      (is (str/includes? failure "declarative-tab-groups isn't on the PATH"))
      (is (str/includes? failure readme))
      (is (= [] @calls)))))
