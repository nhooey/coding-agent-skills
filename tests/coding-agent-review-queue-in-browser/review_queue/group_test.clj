(ns review-queue.group-test
  (:require [clojure.test :refer [deftest is testing]]
            [review-queue.core :as core]
            [review-queue.group :as group]))

(def ^:private pr "https://github.com/o/r/pull/1")
(def ^:private pr2 "https://github.com/o/r/pull/2")
(def ^:private report "https://github.com/o/r/issues/3")
(def ^:private draft "https://github.com/o/r/issues/new")

(defn- item [url kind & {:as more}] (merge {:url url :kind kind :topic "t"} more))

(deftest holds-chunk
  (testing "the group holds the first chunk, or every chunk with all-open"
    (let [p (core/plan 5 [(item pr :merge :topic "a") (item pr2 :merge :topic "a")
                          (item report :report :topic "b") (item (str report "0") :report :topic "b")])]
      (is (= [report (str report "0")] (group/urls (group/group-items p :current-only))))
      (is (= [report (str report "0") pr pr2] (group/urls (group/group-items p :all-open))))))
  (testing "an empty queue holds nothing"
    (is (= [] (group/urls (group/group-items (core/plan 5 []) :current-only))))))

(deftest in-order
  (testing "the chunk's order, a stack side by side bottom first"
    (let [s1 (item pr :merge :stack-id "S" :stack 1)
          s2 (item pr2 :merge :stack-id "S" :stack 2)
          x (item "https://github.com/o/r/pull/7" :merge)]
      (is (= [pr pr2 (:url x)]
             (group/urls (group/group-items (core/plan 5 [s2 x s1]) :current-only)))))))

(deftest on-overview
  (testing "a pull request on files, changes or commits opens on its Overview"
    (is (= [pr pr2 report draft]
           (group/urls [(item (str pr "/files") :merge) (item (str pr2 "/commits") :merge)
                        (item (str report "#issuecomment-1") :report) (item draft :draft)])))))

(deftest told
  (let [items [(item pr :merge) (item report :report :label "the report")]]
    (testing "a group holding items tells the user once, naming the first item"
      (is (= {:title "Review ready" :message "2 to review: o/r#1" :url pr :group "review"}
             (group/notification items))))
    (testing "an item's label names it"
      (is (= "1 to review: the report" (:message (group/notification [(second items)])))))
    (testing "an empty group tells no one"
      (is (nil? (group/notification []))))))

(deftest announcement
  (testing "the review items about to load into the named group, counted"
    (is (= {:title "Review queue"
            :message "Loading 11 review items into the Review tab group"
            :group "review-start"}
           (group/announcement "Review" (vec (repeat 11 pr)))))
    (is (= "Loading 1 review item into the Mine tab group"
           (:message (group/announcement "Mine" [pr])))))
  (testing "nothing to load announces nothing"
    (is (nil? (group/announcement "Review" [])))))

(deftest delivery
  (let [header "GroupID\tTitle\tSubtitle\tMessage\tDelivered At"]
    (testing "a row in the group means it was delivered"
      (is (group/delivered? "review" (str header "\nreview\tReview ready\t\t2 to review\t2026-11-18 10:00:00 +0000"))))
    (testing "only the header, or another group's rows, means it wasn't"
      (is (not (group/delivered? "review" header)))
      (is (not (group/delivered? "review" "")))
      (is (not (group/delivered? "review" (str header "\nreview-start\tReview queue\t\tx\t2026-11-18")))))))
