(ns review-queue.group
  "What the review tab group holds after every reconcile: which items, in
  which order, at which URLs, and the notifications that tell the user."
  (:require [clojure.string :as str]
            [review-queue.core :as core]))

(defn- plain-url
  "The URL an item's tab shows: a pull request's or issue's plain URL, so a
  pull request is on its Overview, else the URL as given."
  [url]
  (or (:url (core/github-ref url)) url))

(defn group-items
  "The items the group holds: the first chunk's, or every chunk's with `:all-open`."
  [{:keys [chunks]} mode]
  (vec (mapcat :items (if (= mode :all-open) chunks (take 1 chunks)))))

(defn urls
  "The URLs the group holds, in the chunks' order, stacks side by side
  bottom first, each pull request on its Overview."
  [items]
  (mapv (comp plain-url :url) items))

(defn- label [{:keys [label url]}]
  (or label
      (when-let [{ref-url :url} (core/github-ref url)]
        (let [[_ owner repo _ number] (str/split (subs ref-url (count "https://github.com")) #"/")]
          (str owner "/" repo "#" number)))
      url))

(defn notification
  "The Review ready notification once the group holds `items`: how many
  there are, and the first one's label and URL. Nil when it holds none."
  [items]
  (when (seq items)
    {:title "Review ready"
     :message (str (count items) " to review: " (label (first items)))
     :url (plain-url (:url (first items)))
     :group "review"}))

(defn announcement
  "The notification sent before the group titled `title` is set, counting
  the review items it will load. Nil when it will load none."
  [title urls]
  (when (seq urls)
    {:title "Review queue"
     :message (str "Loading " (count urls) " review item" (when (< 1 (count urls)) "s")
                   " into the " title " tab group")
     :group "review-start"}))

(defn delivered?
  "Whether `terminal-notifier -list <group>`'s tab-separated output, a
  header row and one row per notification, shows one in `group`."
  [group output]
  (->> (rest (str/split-lines output))
       (some #(= group (first (str/split % #"\t"))))
       boolean))
