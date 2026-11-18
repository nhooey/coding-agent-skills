(ns review-queue.group-test
  (:require [clojure.string :as str]
            [clojure.test :refer [deftest is testing]]
            [review-queue.core :as core]
            [review-queue.group :as group]))

(def ^:private pr "https://github.com/o/r/pull/1")
(def ^:private pr2 "https://github.com/o/r/pull/2")
(def ^:private report "https://github.com/o/r/issues/3")
(def ^:private draft "https://github.com/o/r/issues/new")

(defn- item [url kind & {:as more}] (merge {:url url :kind kind :topic "t"} more))

(defn- ctx [items tabs & {:keys [close?] :or {close? true}}]
  {:items items :tabs tabs :close? close?})

(defn- check [property c] (property c group/no-actions))

(deftest holds-chunk
  (testing "missing items open, in order, at their plain URLs"
    (is (= [report pr]
           (:open (check group/holds-chunk (ctx [(item report :report) (item (str pr "/files") :merge)] []))))))
  (testing "tabs outside the chunk, and second tabs of an item, close"
    (is (= [2 3]
           (:close (check group/holds-chunk
                          (ctx [(item pr :merge)]
                               [{:tabId 1 :url pr} {:tabId 2 :url report} {:tabId 3 :url (str pr "/files")}]))))))
  (testing "a tab on another view of an item's page is that item's tab"
    (is (= {:open [] :close []}
           (select-keys (check group/holds-chunk
                               (ctx [(item pr :merge) (item draft :draft)]
                                    [{:tabId 1 :url (str pr "/files#diff-1")}
                                     {:tabId 2 :url (str draft "?title=Bug")}]))
                        [:open :close]))))
  (testing "with closing off, nothing closes"
    (is (= [] (:close (check group/holds-chunk (ctx [(item pr :merge)] [{:tabId 2 :url report}]
                                                    :close? false))))))
  (testing "new items open after the tabs kept"
    (is (= [draft]
           (:open (check group/holds-chunk
                         (ctx [(item pr :merge) (item report :report) (item draft :draft)]
                              [{:tabId 1 :url pr} {:tabId 2 :url report}])))))))

(deftest in-order
  (testing "kept tabs are re-pointed, in their own slots, to the order"
    (is (= [{:tabId 1 :from report :url pr :for [:order]} {:tabId 2 :from pr :url report :for [:order]}]
           (:repoint (check group/in-order (ctx [(item pr :merge) (item report :report)]
                                                [{:tabId 1 :url report} {:tabId 2 :url pr}]))))))
  (testing "tabs in their slots stay"
    (is (= [] (:repoint (check group/in-order (ctx [(item pr :merge)] [{:tabId 1 :url pr}])))))))

(deftest on-overview
  (testing "a pull request tab on files, changes or commits goes back to its Overview"
    (is (= [{:tabId 1 :from (str pr "/files") :url pr :for [:overview]}
            {:tabId 2 :from (str pr2 "/commits") :url pr2 :for [:overview]}]
           (:repoint (check group/on-overview
                            (ctx [(item pr :merge) (item pr2 :merge) (item report :report)]
                                 [{:tabId 1 :url (str pr "/files")} {:tabId 2 :url (str pr2 "/commits")}
                                  {:tabId 3 :url (str report "#issuecomment-1")}]))))))
  (testing "a pull request tab on its Overview stays"
    (is (= [] (:repoint (check group/on-overview (ctx [(item pr :merge)] [{:tabId 1 :url pr}])))))))

(deftest latest
  (testing "a changed item's tab closes rather than reloading, and the item reopens at its new version"
    (is (= {:open [report] :close [2] :updated [{:tabId 2 :url report}] :repoint []}
           (select-keys (group/reconcile (ctx [(item pr :merge) (item report :report :changed true)]
                                              [{:tabId 1 :url pr} {:tabId 2 :url report}]))
                        [:open :close :updated :repoint]))))
  (testing "a changed item reopens in its place in the order"
    (is (= {:open [pr2] :close [1]
            :repoint [{:tabId 2 :from report :url pr :for [:order]}
                      {:tabId 3 :from pr2 :url report :for [:order]}]}
           (select-keys (group/reconcile (ctx [(item pr :merge :changed true) (item report :report) (item pr2 :merge)]
                                              [{:tabId 1 :url pr} {:tabId 2 :url report} {:tabId 3 :url pr2}]))
                        [:open :close :repoint]))))
  (testing "an unchanged item's tab already shows its latest version, and stays"
    (is (= {:open [] :close [] :updated []}
           (select-keys (group/reconcile (ctx [(item pr :merge)] [{:tabId 1 :url pr}]))
                        [:open :close :updated]))))
  (testing "with all-open, where nothing else closes, a changed item's tab still closes"
    (is (= [1] (:close (group/reconcile (ctx [(item pr :merge :changed true)] [{:tabId 1 :url pr}]
                                             :close? false))))))
  (testing "a draft, or a tab holding a form, is never closed, even when its item changed"
    (is (= {:close [] :updated []}
           (select-keys (group/reconcile (ctx [(item draft :draft :changed true)] [{:tabId 2 :url draft}]))
                        [:close :updated])))
    (is (= {:close [] :updated []}
           (select-keys (group/reconcile (ctx [(item pr :merge :changed true)]
                                              [{:tabId 2 :url pr :untouchable true}]))
                        [:close :updated])))))

(deftest parked
  (testing "while an update is under way, the window sits on a new tab"
    (is (true? (:park (group/reconcile (ctx [(item pr :merge)] [])))))
    (is (true? (:park (group/reconcile (ctx [(item pr :merge :changed true)] [{:tabId 1 :url pr}])))))
    (is (true? (:park (group/reconcile (ctx [(item pr :merge)] [{:tabId 1 :url report}]))))))
  (testing "nothing to update, no new tab"
    (is (false? (:park (group/reconcile (ctx [(item pr :merge)] [{:tabId 1 :url pr}]))))))
  (testing "the new tab is appended last and made the active tab of the browser check's window, its id returned"
    (is (= (str "tell application \"Google Chrome\"\n"
                "  set w to window id 42\n"
                "  set parked to make new tab at end of tabs of w\n"
                "  set active tab index of w to (count of tabs of w)\n"
                "  return id of parked\n"
                "end tell")
           (group/background-script "Google Chrome" 42 (assoc group/no-actions :park true)))))
  (testing "the window is parked before any tab changes, and the parking tab closes after the first tab is active"
    (let [start (group/background-script "Google Chrome" 42 {:park true :repoint [{:from report :url pr}]})
          land (group/focus-script "Google Chrome" 42 pr 77)]
      (is (< (str/index-of start "make new tab") (str/index-of start "set URL to")))
      (is (= (str "tell application \"Google Chrome\"\n"
                  "  set w to window id 42\n"
                  "  set i to 0\n"
                  "  repeat with t in tabs of w\n"
                  "    set i to i + 1\n"
                  "    if URL of t is \"https://github.com/o/r/pull/1\" then\n"
                  "      set active tab index of w to i\n"
                  "      exit repeat\n"
                  "    end if\n"
                  "  end repeat\n"
                  "  try\n"
                  "    close tab id 77 of w\n"
                  "  end try\n"
                  "end tell")
             land)))))

(deftest background
  (testing "the script finds every tab by URL first, then re-points them without activating any"
    (is (= (str "tell application \"Google Chrome\"\n"
                "  set w to window id 42\n"
                "  set found to {}\n"
                "  repeat with u in {\"https://github.com/o/r/issues/3\", \"https://github.com/o/r/pull/1\"}\n"
                "    set hit to missing value\n"
                "    repeat with c in tabs of w\n"
                "      if URL of c is (contents of u) then\n"
                "        set hit to id of c\n"
                "        exit repeat\n"
                "      end if\n"
                "    end repeat\n"
                "    set end of found to hit\n"
                "  end repeat\n"
                "  if item 1 of found is not missing value then tell (tab id (item 1 of found) of w) to set URL to \"https://github.com/o/r/pull/1\"\n"
                "  if item 2 of found is not missing value then tell (tab id (item 2 of found) of w) to set URL to \"https://github.com/o/r/pull/2\"\n"
                "end tell")
           (group/background-script "Google Chrome" 42 {:repoint [{:tabId 1 :from report :url pr}
                                                                  {:tabId 2 :from pr :url pr2}]}))))
  (testing "nothing to park or re-point, no script"
    (is (nil? (group/background-script "Google Chrome" 42 group/no-actions)))))

(deftest focused
  (testing "the first tab kept is the active one"
    (is (= {:tabId 2 :url pr}
           (:focus (check group/focused (ctx [(item pr :merge) (item report :report)]
                                             [{:tabId 9 :url "https://example.com/"} {:tabId 2 :url pr}]))))))
  (testing "with no tab kept, the first one opened"
    (is (= {:url pr} (:focus (check group/focused (ctx [(item (str pr "/files") :merge)] []))))))
  (testing "a fixed first tab keeps the URL it shows"
    (is (= {:tabId 4 :url (str draft "?title=Bug")}
           (:focus (check group/focused (ctx [(item draft :draft) (item pr :merge)]
                                             [{:tabId 4 :url (str draft "?title=Bug")}]))))))
  (testing "the script picks the active tab of the browser check's window, and nothing more"
    (is (= (str "tell application \"Google Chrome\"\n"
                "  set w to window id 42\n"
                "  set i to 0\n"
                "  repeat with t in tabs of w\n"
                "    set i to i + 1\n"
                "    if URL of t is \"https://github.com/o/r/pull/1\" then\n"
                "      set active tab index of w to i\n"
                "      exit repeat\n"
                "    end if\n"
                "  end repeat\n"
                "end tell")
           (group/focus-script "Google Chrome" 42 pr))))
  (testing "no script ever raises the window or the app, or touches the frontmost window"
    (doseq [script [(group/focus-script "Google Chrome" 42 pr)
                    (group/focus-script "Google Chrome" 42 pr 77)
                    (group/background-script "Google Chrome" 42 {:park true :repoint [{:from report :url pr}]})]
            banned ["activate" "set index of" "frontmost"]]
      (is (not (str/includes? script banned)) banned))))

(deftest untouchable
  (let [s1 (item pr :merge :stack-id "S" :stack 1)
        s2 (item pr2 :merge :stack-id "S" :stack 2)
        x (item "https://github.com/o/r/pull/7" :merge)
        y (item "https://github.com/o/r/pull/8" :merge)
        form {:tabId 5 :url "https://github.com/o/other/issues/new" :untouchable true}]
    (testing "a tab holding a form is never re-pointed or closed, even when its item changed"
      (let [a (group/reconcile (ctx [(assoc x :changed true)] [{:tabId 1 :url (:url y)} form]))]
        (is (not-any? #{5} (map :tabId (concat (:repoint a) (:updated a)))))
        (is (not-any? #{5} (:close a)))))
    (testing "a stack around a fixed tab stays together, with the fixed tab just after it"
      (is (= [{:tabId 1 :url pr} {:tabId 2 :url pr2} {:tabId 3 :url (:url x)}]
             (mapv #(select-keys % [:tabId :url])
                   (:repoint (group/reconcile (ctx [x s1 s2 y]
                                                   [{:tabId 1 :url (:url x)} {:tabId 2 :url pr}
                                                    form
                                                    {:tabId 3 :url pr2} {:tabId 4 :url (:url y)}])))))))
    (testing "a stack bigger than the slots before a fixed tab goes after it, singles filling in"
      (is (= [{:tabId 1 :url (:url x)}]
             (mapv #(select-keys % [:tabId :url])
                   (:repoint (group/reconcile (ctx [s1 s2 x] [{:tabId 1 :url pr} form]))))))
      (is (= [pr pr2] (:open (group/reconcile (ctx [s1 s2 x] [{:tabId 1 :url pr} form]))))))))

(deftest told
  (let [items [(item pr :merge) (item report :report :label "the report")]]
    (testing "an item opened tells the user once, naming the first item"
      (is (= {:title "Review ready" :message "2 to review: o/r#1" :url pr :group "review"}
             (:notification (group/told (ctx items []) (assoc group/no-actions :open [report]))))))
    (testing "so does a changed item"
      (is (some? (:notification (check group/told (ctx (assoc-in items [1 :changed] true)
                                                       [{:tabId 1 :url pr} {:tabId 2 :url report}]))))))
    (testing "an item's label names it"
      (is (= "1 to review: the report"
             (:message (:notification (group/told (ctx [(second items)] [])
                                                  (assoc group/no-actions :open [report])))))))
    (testing "a reorder alone tells no one"
      (is (nil? (:notification (check group/told (ctx items [{:tabId 1 :url pr}
                                                             {:tabId 2 :url report}]))))))))

(deftest reconcile
  (testing "every property in order, one re-point per tab naming why, and only changed items close and reopen"
    (is (= {:open [pr2 draft]
            :repoint [{:tabId 1 :from report :url pr :for [:order]}
                      {:tabId 2 :from (str pr "/files") :url report :for [:order]}]
            :updated [{:tabId 4 :url pr2}]
            :close [9 4]
            :park true
            :focus {:tabId 1 :url pr}
            :notification {:title "Review ready" :message "4 to review: o/r#1" :url pr :group "review"}}
           (group/reconcile (ctx [(item pr :merge) (item report :report) (item pr2 :merge :changed true)
                                  (item draft :draft)]
                                 [{:tabId 1 :url report} {:tabId 9 :url "https://example.com/"}
                                  {:tabId 2 :url (str pr "/files")} {:tabId 4 :url pr2}])))))
  (testing "the group holds the first chunk, or every chunk with all-open"
    (let [p (core/plan 5 [(item pr :merge :topic "a") (item pr2 :merge :topic "a")
                          (item report :report :topic "b") (item (str report "0") :report :topic "b")])
          tabs [{:tabId 1 :url pr}]]
      (is (= {:open [report (str report "0")] :close [1]}
             (select-keys (group/for-plan p :current-only tabs) [:open :close])))
      (is (= {:open [(str report "0") pr pr2] :close []
              :repoint [{:tabId 1 :from pr :url report :for [:order]}]}
             (select-keys (group/for-plan p :all-open tabs) [:open :close :repoint]))))))

(deftest announcement
  (testing "every step that will happen, as a nested list, before anything happens"
    (is (= {:title "Review queue"
            :message (str "Opening the review queue in Google Chrome:\n"
                          "• Launch Google Chrome\n"
                          "• Wait for its extension\n"
                          "• Open a new window\n"
                          "• Load 11 review items")
            :group "review-start"}
           (group/announcement "Google Chrome" {:launch true :open-window true}
                               {:open (vec (repeat 11 pr))}))))
  (testing "the new tab shown while updating, and only the items that close or open, each counted"
    (is (= (str "Opening the review queue in Google Chrome:\n"
                "• Show a new tab while updating\n"
                "• Close 2 changed review items\n"
                "• Load 1 review item")
           (:message (group/announcement "Google Chrome" {}
                                         {:open [pr] :updated [{} {}] :repoint [{}] :park true})))))
  (testing "a step that won't happen is left out"
    (is (= "Opening the review queue in Google Chrome:\n• Open a new window"
           (:message (group/announcement "Google Chrome" {:open-window true} group/no-actions)))))
  (testing "nothing to do announces nothing"
    (is (nil? (group/announcement "Google Chrome" {} group/no-actions)))))

(deftest delivery
  (let [header "GroupID\tTitle\tSubtitle\tMessage\tDelivered At"]
    (testing "a row in the group means it was delivered"
      (is (group/delivered? "review" (str header "\nreview\tReview ready\t\t2 to review\t2026-11-18 10:00:00 +0000"))))
    (testing "only the header, or another group's rows, means it wasn't"
      (is (not (group/delivered? "review" header)))
      (is (not (group/delivered? "review" "")))
      (is (not (group/delivered? "review" (str header "\nreview-start\tReview queue\t\tx\t2026-11-18")))))))
