(ns review-queue.core-test
  (:require [clojure.test :refer [deftest is testing]]
            [review-queue.core :as core]))

(defn- item [url kind topic & {:as more}]
  (merge {:url url :kind kind :topic topic} more))

(defn- urls [chunk] (mapv :url (:items chunk)))

(deftest order
  (testing "blocking decisions and reports, then merges, then the rest"
    (is (= ["d" "r" "m" "v"]
           (mapv :url (core/ordered [(item "v" :review "t")
                                     (item "m" :merge "t")
                                     (item "r" :report "t")
                                     (item "d" :decision "t")])))))
  (testing "an explicit priority overrides the kind's"
    (is (= ["v" "m"]
           (mapv :url (core/ordered [(item "m" :merge "t")
                                     (item "v" :review "t" :priority 0)])))))
  (testing "topics keep the order they first appear in"
    (is (= ["b1" "b2" "a1"]
           (mapv :url (core/ordered [(item "b1" :review "b")
                                     (item "a1" :review "a")
                                     (item "b2" :review "b")])))))
  (testing "a stack merges bottom-up"
    (is (= ["s1" "s2" "s3"]
           (mapv :url (core/ordered [(item "s3" :merge "t" :stack 3)
                                     (item "s1" :merge "t" :stack 1)
                                     (item "s2" :merge "t" :stack 2)])))))
  (testing "deferred items go after everything else"
    (is (= ["v" "d"]
           (mapv :url (core/ordered [(item "d" :decision "t" :deferred true)
                                     (item "v" :review "t")]))))))

(deftest chunking
  (testing "one topic per chunk"
    (is (= [["a1" "a2"] ["b1"]]
           (mapv urls (:chunks (core/plan 5 [(item "a1" :review "a")
                                             (item "b1" :review "b")
                                             (item "a2" :review "a")]))))))
  (testing "a big topic splits into even chunks, not a full one and a scrap"
    (is (= [4 3]
           (mapv (comp count :items)
                 (:chunks (core/plan 5 (for [i (range 7)] (item (str i) :review "t"))))))))
  (testing "chunks are numbered from 1 and name their topic"
    (is (= [{:chunk 1 :topic "a"} {:chunk 2 :topic "b"}]
           (mapv #(select-keys % [:chunk :topic])
                 (:chunks (core/plan 5 [(item "a1" :review "a") (item "a2" :review "a")
                                        (item "b1" :review "b") (item "b2" :review "b")]))))))
  (testing "one-item topics share a mixed chunk, after the bigger topics"
    (is (= [{:topic "a" :urls ["a1" "a2"]} {:topic "mixed" :urls ["x" "y" "z"]}]
           (mapv (fn [c] {:topic (:topic c) :urls (urls c)})
                 (:chunks (core/plan 5 [(item "x" :review "x")
                                        (item "a1" :review "a")
                                        (item "y" :review "y")
                                        (item "a2" :review "a")
                                        (item "z" :review "z")]))))))
  (testing "a mixed chunk keeps the order, across priorities too"
    (is (= [["d" "r" "m"] ["v1" "v2"]]
           (mapv urls (:chunks (core/plan 5 [(item "v1" :review "v") (item "v2" :review "v")
                                             (item "m" :merge "m") (item "r" :report "r")
                                             (item "d" :decision "d")]))))))
  (testing "a lone one-item topic keeps its own name"
    (is (= ["b"] (mapv :topic (:chunks (core/plan 5 [(item "b1" :review "b")]))))))
  (testing "a big mixed chunk splits evenly too"
    (is (= [4 3]
           (mapv (comp count :items)
                 (:chunks (core/plan 5 (for [i (range 7)] (item (str i) :review (str i))))))))))

(deftest finished-items
  (let [{:keys [chunks finished]}
        (core/plan 5 [(item "merged" :merge "t" :state "MERGED")
                      (item "closed" :review "t" :state "CLOSED")
                      (item "said-done" :draft "t" :done true)
                      (item "open" :merge "t" :state "OPEN")])]
    (is (= [["open"]] (mapv urls chunks)))
    (is (= ["merged" "closed" "said-done"] (mapv :url finished)))))

(deftest github-refs
  (is (= {:type :pr :url "https://github.com/o/r/pull/12"}
         (core/github-ref "https://github.com/o/r/pull/12/files")))
  (is (= {:type :issue :url "https://github.com/o/r/issues/3"}
         (core/github-ref "https://github.com/o/r/issues/3#issuecomment-1")))
  (testing "nothing to fetch"
    (is (nil? (core/github-ref "https://github.com/o/r/issues/new")))
    (is (nil? (core/github-ref "https://example.com/o/r/pull/1")))
    (is (nil? (core/github-ref "not a url")))))

(deftest input
  (testing "JSON kinds become keywords"
    (is (= [{:url "u" :kind :merge :topic "t" :stack 1}]
           (core/normalize [{:url "u" :kind "merge" :topic "t" :stack 1}]))))
  (testing "problems name the item and what is wrong"
    (is (= ["item 1: :kind must be one of decision, draft, merge, report, review"
            "item 2: :url is missing"
            "item 2: :topic is missing"]
           (core/problems (core/normalize [{:url "u" :kind "nope" :topic "t"}
                                           {:kind "review"}]))))))

(def ^:private report "https://github.com/o/r/issues/2")

(defn- open-pr [n base head] {:url (str "https://github.com/o/r/pull/" n) :base base :head head})

(def ^:private open-prs
  "A three-PR stack, 1 at the bottom on main, 2 on 1 and 3 on 2, and a lone PR 9."
  [(open-pr 3 "b2" "b3") (open-pr 1 "main" "b1") (open-pr 2 "b1" "b2") (open-pr 9 "main" "b9")])

(defn- n [k] (str "https://github.com/o/r/pull/" k))

(deftest stacks
  (testing "the repositories to list open pull requests from"
    (is (= ["github.com/o/r"]
           (core/pr-repos [(item (str (n 1) "/files") :merge "t") (item (n 2) :merge "t")
                           (item report :report "t")]))))
  (testing "a chain of bases and heads is a stack, bottom first; a lone PR isn't"
    (is (= {(n 1) {:stack-id (n 1) :stack 1}
            (n 2) {:stack-id (n 1) :stack 2}
            (n 3) {:stack-id (n 1) :stack 3}}
           (core/stack-info open-prs))))
  (testing "a stack member brings its stack's other open members, with its kind and topic"
    (is (= [{:url (n 2) :kind :merge :topic "t" :stack-id (n 1) :stack 2}
            {:url (n 1) :kind :merge :topic "t" :stack-id (n 1) :stack 1}
            {:url (n 3) :kind :merge :topic "t" :stack-id (n 1) :stack 3}]
           (core/with-stacks [(item (n 2) :merge "t")] open-prs))))
  (testing "a member already in the queue, done or not, isn't brought twice"
    (is (= [(n 2) (n 3) (n 1)]
           (mapv :url (core/with-stacks [(item (n 2) :merge "t") (item (n 3) :merge "t" :done true)]
                                        open-prs)))))
  (testing "the stack sits, bottom first and nothing between, where its first member is"
    (is (= [(n 9) (n 1) (n 2) (n 3) "x"]
           (mapv :url (core/ordered (core/with-stacks [(item (n 9) :review "t")
                                                       (item (n 3) :review "t")
                                                       (item "x" :review "t")
                                                       (item (n 1) :review "u")]
                                                      open-prs))))))
  (testing "members from other topics join the first member's topic and chunk"
    (is (= [[(n 1) (n 2) (n 3)]]
           (mapv urls (:chunks (core/plan 5 (core/with-stacks [(item (n 2) :merge "a")
                                                               (item (n 1) :merge "b")]
                                                              open-prs)))))))
  (testing "a chunk never splits a stack"
    (is (= [[(n 1) (n 2) (n 3)] ["x" "y"]]
           (mapv urls (:chunks (core/plan 3 (core/with-stacks [(item (n 1) :merge "t")
                                                               (item "x" :merge "t")
                                                               (item "y" :merge "t")]
                                                              open-prs))))))))
