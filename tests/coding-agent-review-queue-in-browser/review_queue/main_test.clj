(ns review-queue.main-test
  (:require [clojure.test :refer [deftest is testing]]
            [review-queue.group :as group]
            [review-queue.main :as main]))

(def ^:private pr "https://github.com/o/r/pull/1")

(def ^:private header "GroupID\tTitle\tSubtitle\tMessage\tDelivered At")

(defn- recorded
  "Stubs of afplay, terminal-notifier and osascript: `found` names the
  commands on the path, and `listed` is what `terminal-notifier -list`
  prints. Every call lands in the returned atom, tagged by how it ran."
  [found listed]
  (let [calls (atom [])]
    [calls {:run (fn [cmd] (swap! calls conj [:run cmd])
                   {:out (if (= "-list" (second cmd)) listed "")})
            :spawn (fn [cmd] (swap! calls conj [:spawn cmd]))
            :which #(contains? found %)
            :sleep (fn [ms] (swap! calls conj [:sleep ms]))}]))

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
  (testing "the steps show with the sound in their own group, then it waits 1 second"
    (let [[calls env] (recorded #{"terminal-notifier"} (str header "\nreview-start\tReview queue\t\tx\t2026"))
          steps (group/announcement "Google Chrome" {:launch true} {:open [pr pr pr]})]
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

(deftest apply-in-background
  (testing "osascript re-points in the browser check's window, with no extension tool"
    (let [[calls env] (recorded #{} "")
          actions {:repoint [{:tabId 1 :from "https://a/1" :url pr}]}]
      (is (= {:applied true} (main/apply! "Google Chrome" 42 actions env)))
      (is (= [[:run ["osascript" "-e" (group/background-script "Google Chrome" 42 actions)]]] @calls))))
  (testing "parking on a new tab returns the parking tab's id, for closing it when the update lands"
    (let [[calls env] (recorded #{} "")
          env (assoc env :run (fn [cmd] (swap! calls conj [:run cmd]) {:out "77\n"}))
          actions (assoc group/no-actions :park true)]
      (is (= {:applied true :parked 77} (main/apply! "Google Chrome" 42 actions env)))
      (is (= [[:run ["osascript" "-e" (group/background-script "Google Chrome" 42 actions)]]] @calls))))
  (testing "nothing to park or re-point runs nothing"
    (let [[calls env] (recorded #{} "")]
      (is (= {:applied false} (main/apply! "Google Chrome" 42 group/no-actions env)))
      (is (= [] @calls)))))

(deftest focus
  (testing "osascript runs the focus script for the browser check's app and window"
    (let [[calls env] (recorded #{} "")]
      (main/focus! "Google Chrome" 42 pr nil env)
      (is (= [[:run ["osascript" "-e" (group/focus-script "Google Chrome" 42 pr)]]] @calls))))
  (testing "with --unpark, the same script then closes the parking tab"
    (let [[calls env] (recorded #{} "")]
      (main/focus! "Google Chrome" 42 pr 77 env)
      (is (= [[:run ["osascript" "-e" (group/focus-script "Google Chrome" 42 pr 77)]]] @calls))))
  (testing "--unpark takes the parking tab's id"
    (is (= 77 (:unpark (main/options ["--focus-window" "42" "--unpark" "77"]))))))
