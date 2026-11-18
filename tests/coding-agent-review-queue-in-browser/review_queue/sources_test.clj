(ns review-queue.sources-test
  "The skill drives the browser only through declarative-tab-groups: its
  one osascript call is the notification fallback, and nothing in it
  brings a window or a tab forward."
  (:require [babashka.fs :as fs]
            [clojure.java.io :as io]
            [clojure.string :as str]
            [clojure.test :refer [deftest is testing]]
            [edamame.core :as e]))

(def ^:private skill
  "The skill's folder: `scripts/src/review_queue/main.clj` is in it."
  (-> (io/resource "review_queue/main.clj") io/file fs/parent fs/parent fs/parent fs/parent))

(defn- files [glob] (map str (fs/glob skill glob)))

(defn- names-osascript? [x]
  (and (or (string? x) (symbol? x) (keyword? x)) (str/includes? (str x) "osascript")))

(deftest osascript-only-notifies
  (testing "in the program, only notify!, the notification fallback, names osascript"
    (is (= #{'notify!}
           (set (for [file (files "**.clj")
                      form (e/parse-string-all (slurp file) {:all true :auto-resolve-ns true})
                      :when (some names-osascript? (tree-seq coll? seq form))]
                  (second form))))))
  (testing "in the docs, osascript is named only as terminal-notifier's fallback"
    (doseq [file (files "**.md")
            line (str/split-lines (slurp file))
            :when (str/includes? line "osascript")]
      (is (str/includes? line "terminal-notifier") line))))

(deftest nothing-comes-forward
  (testing "no file of the skill activates an app, picks a window's active tab or raises a window"
    (is (seq (files "**")))
    (doseq [file (files "**")
            :when (fs/regular-file? file)
            banned ["activate" "set active tab" "set index of window"]]
      (is (not (str/includes? (str/lower-case (slurp file)) banned)) (str file ": " banned)))))
