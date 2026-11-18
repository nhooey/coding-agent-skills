(ns review-queue.core
  "The review queue's pure part: which items are finished, their stacks,
  their order and their chunks. An item is a map of `:url`, `:kind`,
  `:topic` and, optionally, `:priority` (lower first), `:stack` (1 is the
  bottom), `:stack-id`, `:label`, `:changed`, `:done`, `:deferred` and
  `:state`, the GitHub state fetched for it."
  (:require [clojure.string :as str]))

(def kinds #{:decision :report :merge :review :draft})

(def ^:private kind-priority {:decision 0 :report 1 :merge 2})

(def ^:private finished-states #{"MERGED" "CLOSED"})

(defn normalize [items]
  (mapv (fn [{:keys [kind] :as it}]
          (cond-> it (some? kind) (assoc :kind (keyword (name kind)))))
        items))

(defn problems [items]
  (for [[i it] (map-indexed (fn [i it] [(inc i) it]) items)
        problem [(when-not (contains? kinds (:kind it))
                   (str ":kind must be one of " (str/join ", " (sort (map name kinds)))))
                 (when-not (string? (:url it)) ":url is missing")
                 (when-not (string? (:topic it)) ":topic is missing")]
        :when problem]
    (str "item " i ": " problem)))

(defn priority [{:keys [priority kind]}]
  (or priority (get kind-priority kind 3)))

(defn finished? [{:keys [done state]}]
  (or (true? done) (contains? finished-states state)))

(defn- tier [it] [(boolean (:deferred it)) (priority it)])

(defn stack-id
  "The stack an item belongs to: its `:stack-id`, else its topic when it has
  a `:stack` position."
  [it]
  (or (:stack-id it) (when (:stack it) [:topic (:topic it)])))

(defn- join-stacks
  "Gives each stack's members the topic, priority and deferral of its first
  member, by `key`, so the stack sits there as one run."
  [key items]
  (let [first-member (into {} (for [[sid ms] (group-by stack-id (filter stack-id items))]
                                [sid (first (sort-by key ms))]))]
    (mapv (fn [it]
            (if-let [a (first-member (stack-id it))]
              (-> it
                  (assoc :topic (:topic a) :priority (priority a))
                  (cond-> (:deferred a) (assoc :deferred true)
                    (not (:deferred a)) (dissoc :deferred))
                  (assoc ::anchor (::i a)))
              (assoc it ::anchor (::i it))))
          items)))

(defn ordered
  "Deferred items last, then by priority; within a priority, topics in the
  order they first appear, one-item topics after the bigger ones. A stack
  sits where its first member is, bottom first, with nothing between."
  [items]
  (let [indexed (map-indexed (fn [i it] (assoc it ::i i)) items)
        rank-of (fn [its] (zipmap (distinct (map :topic its)) (range)))
        first-rank (rank-of indexed)
        joined (join-stacks (fn [it] [(if (:deferred it) 1 0) (priority it)
                                      (first-rank (:topic it)) (::i it)])
                            indexed)
        topic-rank (rank-of joined)
        topic-size (frequencies (map (juxt tier :topic) joined))]
    (->> joined
         (sort-by (fn [it]
                    [(if (:deferred it) 1 0)
                     (priority it)
                     (if (= 1 (topic-size [(tier it) (:topic it)])) 1 0)
                     (topic-rank (:topic it))
                     (::anchor it)
                     (or (:stack it) 0)
                     (::i it)]))
         (mapv #(dissoc % ::i ::anchor)))))

(defn- units
  "Runs of one stack's members, and every other item alone."
  [items]
  (reduce (fn [acc it]
            (let [sid (stack-id it)]
              (if (and sid (seq acc) (= sid (stack-id (first (peek acc)))))
                (conj (pop acc) (conj (peek acc) it))
                (conj acc [it]))))
          [] items))

(defn- split-evenly
  "Splits `items` into the fewest pieces of at most `size`, as even as can
  be, never splitting a stack; a stack bigger than `size` is one piece."
  [size items]
  (loop [us (units items)
         left (count items)
         pieces (quot (+ left size -1) size)
         acc []]
    (if (empty? us)
      acc
      (let [target (quot (+ left (max pieces 1) -1) (max pieces 1))
            [taken used] (reduce (fn [[taken used] u]
                                   (if (and (seq taken) (> (+ (count taken) (count u)) target))
                                     (reduced [taken used])
                                     [(into taken u) (inc used)]))
                                 [[] 0] us)]
        (recur (drop used us) (- left (count taken)) (dec pieces) (conj acc taken))))))

(defn- gather-singles
  "Joins each run of adjacent one-item groups into one group."
  [groups]
  (->> groups
       (partition-by #(= 1 (count %)))
       (mapcat (fn [run] (if (= 1 (count (first run))) [(vec (apply concat run))] run)))))

(defn- chunk-topic [items]
  (let [topics (distinct (map :topic items))]
    (if (= 1 (count topics)) (first topics) "mixed")))

(defn plan
  "The chunks of the unfinished items, in order, and the finished items.
  Each chunk is one topic, except that adjacent one-item topics share a
  `mixed` chunk."
  [size items]
  (let [{finished true remaining false} (group-by (comp boolean finished?) items)]
    {:chunks (->> (ordered remaining)
                  (partition-by (juxt tier :topic))
                  gather-singles
                  (mapcat (partial split-evenly size))
                  (map-indexed (fn [i xs] {:chunk (inc i) :topic (chunk-topic xs) :items xs}))
                  vec)
     :finished (vec finished)}))

(defn github-ref
  "The pull request or issue a github.com URL points at, or nil."
  [url]
  (let [uri (try (java.net.URI. url) (catch Exception _ nil))
        [_ owner repo section number] (some-> uri .getPath (str/split #"/"))]
    (when (and uri (= "github.com" (.getHost uri)) owner repo
               (#{"pull" "issues"} section) (some-> number parse-long))
      {:type (if (= section "pull") :pr :issue)
       :url (str "https://github.com/" owner "/" repo "/" section "/" number)})))

(defn page
  "What makes two URLs the same item: the pull request or issue, else the
  URL without its query, fragment or trailing slash."
  [url]
  (or (:url (github-ref url))
      (when-let [uri (try (java.net.URI. url) (catch Exception _ nil))]
        (let [path (or (.getPath uri) "")]
          (str (.getScheme uri) "://" (.getHost uri)
               (cond-> path (str/ends-with? path "/") (subs 0 (dec (count path)))))))
      url))

(defn- repo-of [url]
  (let [u (:url (github-ref url))]
    (subs u 0 (str/last-index-of u "/pull/"))))

(defn pr-repos
  "The repositories of the queue's pull requests, as `github.com/owner/name`."
  [items]
  (->> items
       (filter #(= :pr (:type (github-ref (:url %)))))
       (map #(subs (repo-of (:url %)) (count "https://")))
       distinct
       vec))

(defn stack-info
  "The stacks among `open-prs` (maps of `:url`, `:base` and `:head`, as
  `gh pr list` gives them): a pull request whose base is another's head
  branch, in the same repository, sits on it. Maps each member of a stack
  of 2 or more to its `:stack-id`, the bottom's URL, and its `:stack`
  position, 1 at the bottom."
  [open-prs]
  (into {}
        (for [[_ prs] (group-by (comp repo-of :url) open-prs)
              :let [by-head (into {} (map (juxt :head identity)) prs)
                    parent #(let [p (by-head (:base %))] (when (not= p %) p))
                    chain (fn [pr] (take-while some? (take (inc (count prs)) (iterate parent pr))))
                    placed (for [pr prs :let [c (chain pr)]]
                             [(:url pr) {:stack-id (:url (last c)) :stack (count c)}])
                    sizes (frequencies (map (comp :stack-id second) placed))]
              [url info] placed
              :when (< 1 (sizes (:stack-id info)))]
          [url info])))

(defn with-stacks
  "Adds stack positions to the queue's pull requests from `open-prs`, and
  brings in each stack's open members the queue lacks, with the kind and
  topic of the stack's first member in the queue. An item's own
  `:stack-id` and `:stack` win."
  [items open-prs]
  (let [info (stack-info open-prs)
        placed (mapv (fn [it] (merge (info (page (:url it))) it)) items)
        present (set (map (comp page :url) placed))
        first-member (reduce (fn [m it] (cond-> m (and (:stack-id it) (not (m (:stack-id it))))
                                          (assoc (:stack-id it) it)))
                             {} placed)]
    (into placed
          (sort-by (juxt :stack-id :stack)
                   (for [pr open-prs
                         :let [s (info (:url pr))
                               a (some-> s :stack-id first-member)]
                         :when (and a (not (present (:url pr))))]
                     (merge (select-keys a [:kind :topic :priority :deferred]) {:url (:url pr)} s))))))
