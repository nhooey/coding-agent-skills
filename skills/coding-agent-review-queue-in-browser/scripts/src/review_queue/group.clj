(ns review-queue.group
  "The end state the session's tab group reaches after every reconcile, one
  function per property, checked in order by `reconcile`. Each takes the
  reconcile's context and the actions so far, and adds what makes its
  property hold. The context is `:items`, what the group holds, in order,
  `:tabs`, the group's tabs in its order (maps of `:tabId`, `:url` and,
  for a tab holding an unsubmitted form, `:untouchable`), and `:close?`."
  (:require [clojure.string :as str]
            [review-queue.core :as core]))

(def no-actions {:open [] :repoint [] :updated [] :close []})

(defn- plain-url
  "The URL an item's tab shows: a pull request's or issue's plain URL, so a
  pull request is on its Overview, else the URL as given."
  [url]
  (or (:url (core/github-ref url)) url))

(defn- units
  "Runs of one stack's members, and every other item alone."
  [items]
  (reduce (fn [acc it]
            (let [sid (core/stack-id it)]
              (if (and sid (seq acc) (= sid (core/stack-id (first (peek acc)))))
                (conj (pop acc) (conj (peek acc) it))
                (conj acc [it]))))
          [] items))

(defn- fill
  "Fills a run of `cap` movable slots from `queue`, a list of units, in
  order. A stack that would straddle the run's end ends the run instead,
  and the units it displaces go after it, past the fixed tab."
  [cap queue]
  (loop [placed [] q queue]
    (let [u (first q)
          room (- cap (count (apply concat placed)))]
      (cond
        (or (nil? u) (<= room 0)) [placed q]
        (<= (count u) room) (recur (conj placed u) (rest q))
        (<= (count u) cap)
        (let [popped (loop [kept placed popped ()]
                       (if (>= (- cap (count (apply concat kept))) (count u))
                         [kept popped]
                         (recur (pop kept) (cons (peek kept) popped))))
              [kept popped] popped
              spare (- cap (count (apply concat kept)) (count u))
              [back after] (loop [back [] left popped]
                             (let [p (first left)]
                               (if (and p (<= (+ (count (apply concat back)) (count p)) spare))
                                 (recur (conj back p) (rest left))
                                 [back left])))]
          [(-> kept (into back) (conj u)) (concat after (rest q))])
        :else
        (let [[more q'] (fill room (remove #(< 1 (count %)) (rest q)))
              taken (set (apply concat more))]
          [(into placed more) (cons u (remove #(taken (first %)) (rest q)))])))))

(defn- updating
  "The tabs of `:changed` items, which close so the items reopen at their
  new version, except a tab holding a form or a draft."
  [{:keys [items tabs]}]
  (let [page (comp core/page :url)
        changed (set (map page (filter :changed items)))
        drafts (set (map page (filter #(= :draft (:kind %)) items)))]
    (filterv #(and (changed (page %)) (not (:untouchable %)) (not (drafts (page %)))) tabs)))

(defn layout
  "Each tab's slot, in the group's order, and what it shows: a fixed tab,
  one that is `:untouchable` or holds a draft (or, without `:close?`, one
  outside the chunk), keeps its page; a movable tab gets the next item in
  order, or nothing, and the items left over open after the last tab. A
  changed item's tab is left out, since it closes, so the item reopens in
  its place in the order."
  [{:keys [items close?] :as c}]
  (let [page (comp core/page :url)
        tabs (remove (set (updating c)) (:tabs c))
        wanted (set (map page items))
        drafts (set (map page (filter #(= :draft (:kind %)) items)))
        fixed? #(or (:untouchable %) (drafts (page %)) (and (not close?) (not (wanted (page %)))))
        shown (set (map page (filter fixed? tabs)))
        movable (reduce (fn [acc t]
                          (let [p (page t)]
                            (if (and (not (fixed? t)) (wanted p) (not (shown p))
                                     (not-any? #(= p (page %)) acc))
                              (conj acc t)
                              acc)))
                        [] tabs)
        slots (filter #(or (fixed? %) (some #{%} movable)) tabs)
        runs (partition-by fixed? slots)
        queue (units (remove #(shown (page %)) items))
        [placed left]
        (reduce (fn [[placed q] [run last?]]
                  (if (fixed? (first run))
                    [(into placed (map (fn [t] {:tab t :fixed true}) run)) q]
                    (let [[us q'] (if last? [q ()] (fill (count run) q))
                          its (vec (apply concat us))]
                      [(into placed (map-indexed (fn [i t] {:tab t :item (get its i)}) run))
                       (if last? (map vector (drop (count run) its)) q')])))
                [[] queue]
                (map vector runs (concat (repeat (dec (count runs)) false) [true])))]
    {:slots placed
     :open (vec (apply concat left))
     :extra (vec (remove (set slots) tabs))}))

(defn- repoint
  "Adds a re-point of `tab` to `url`, for `why`, once per tab."
  [actions tab url why]
  (let [i (first (keep-indexed (fn [i n] (when (= (:tabId n) (:tabId tab)) i)) (:repoint actions)))]
    (if i
      (update-in actions [:repoint i :for] conj why)
      (update actions :repoint conj {:tabId (:tabId tab) :from (:url tab) :url url :for [why]}))))

(defn holds-chunk
  "One tab per item of the chunk, and nothing else: the missing items
  open, and every other tab closes, except a fixed one."
  [c actions]
  (let [{:keys [slots open extra]} (layout c)]
    (assoc actions
           :open (mapv (comp plain-url :url) open)
           :close (if (:close? c)
                    (into (mapv :tabId extra)
                          (keep #(when (and (not (:fixed %)) (nil? (:item %))) (:tabId (:tab %))) slots))
                    []))))

(defn- moving [c]
  (filter #(and (:item %) (not (:fixed %))) (:slots (layout c))))

(defn in-order
  "The tabs in the chunk's order, stacks side by side bottom first: no tool
  moves a tab, so a movable tab showing another item is re-pointed."
  [c actions]
  (reduce (fn [a {:keys [tab item]}]
            (cond-> a (not= (core/page (:url tab)) (core/page (:url item)))
                    (repoint tab (plain-url (:url item)) :order)))
          actions (moving c)))

(defn on-overview
  "Every pull request tab on its Overview, its plain `/pull/<n>` URL."
  [c actions]
  (reduce (fn [a {:keys [tab item]}]
            (cond-> a (and (= (core/page (:url tab)) (core/page (:url item)))
                           (= :pr (:type (core/github-ref (:url tab))))
                           (not= (:url tab) (plain-url (:url tab))))
                    (repoint tab (plain-url (:url item)) :overview)))
          actions (moving c)))

(defn latest
  "Every tab at its item's latest version: when the update starts, a
  `:changed` item's tab closes, rather than reloading in place, and the
  item reopens at its new version, in its place in the order, since
  `layout` leaves that tab out. A tab holding a form or a draft never
  closes. A tab whose item didn't change already shows its latest version."
  [c actions]
  (let [stale (updating c)]
    (-> actions
        (assoc :updated (mapv #(select-keys % [:tabId :url]) stale))
        (update :close into (map :tabId stale)))))

(defn parked
  "While an update is under way, whenever a tab opens, closes or is
  re-pointed, the window's active tab is a new tab, Chrome's new tab page,
  so the user sees a neutral page rather than a half-updated item."
  [_ actions]
  (assoc actions :park (boolean (some seq ((juxt :open :repoint :close) actions)))))

(defn focused
  "When the update lands, the group's first tab the active tab of its
  window, and the parking tab closed, without raising the window or the
  app: the first tab's id and the URL it shows, or with no tab kept, the
  first URL opened."
  [c actions]
  (let [{:keys [slots open]} (layout c)
        first-slot (first (filter #(or (:fixed %) (:item %)) slots))]
    (assoc actions :focus
           (cond
             (:fixed first-slot) {:tabId (:tabId (:tab first-slot)) :url (:url (:tab first-slot))}
             first-slot {:tabId (:tabId (:tab first-slot)) :url (plain-url (:url (:item first-slot)))}
             (seq open) {:url (plain-url (:url (first open)))}))))

(defn- label [{:keys [label url]}]
  (or label
      (when-let [{ref-url :url} (core/github-ref url)]
        (let [[_ owner repo _ number] (str/split (subs ref-url (count "https://github.com")) #"/")]
          (str owner "/" repo "#" number)))
      url))

(defn told
  "The user told once, when an item opened or changed: how many items the
  group holds, and the first one's label and URL."
  [{:keys [items]} actions]
  (cond-> actions
    (and (seq items) (or (seq (:open actions)) (some :changed items)))
    (assoc :notification {:title "Review ready"
                          :message (str (count items) " to review: " (label (first items)))
                          :url (plain-url (:url (first items)))
                          :group "review"})))

(defn announcement
  "The notification sent before a reconcile starts, listing only the steps
  that will happen: launching `app` and waiting for its extension, opening
  a new window, showing a new tab while updating, closing the `:updated`
  items' tabs and loading the `:open` review items. Nil when none will."
  [app {:keys [launch open-window]} {:keys [open updated park]}]
  (let [items (fn [xs kind] (str (count xs) kind " review item" (when (< 1 (count xs)) "s")))
        steps (cond-> []
                launch (conj (str "Launch " app) "Wait for its extension")
                open-window (conj "Open a new window")
                park (conj "Show a new tab while updating")
                (seq updated) (conj (str "Close " (items updated " changed")))
                (seq open) (conj (str "Load " (items open ""))))]
    (when (seq steps)
      {:title "Review queue"
       :message (str/join "\n" (cons (str "Opening the review queue in " app ":")
                                     (map #(str "• " %) steps)))
       :group "review-start"})))

(defn delivered?
  "Whether `terminal-notifier -list <group>`'s tab-separated output, a
  header row and one row per notification, shows one in `group`."
  [group output]
  (->> (rest (str/split-lines output))
       (some #(= group (first (str/split % #"\t"))))
       boolean))

(def properties [holds-chunk in-order on-overview latest parked focused told])

(defn reconcile
  "The actions that bring the group to its end state, each property in order."
  [c]
  (reduce (fn [actions property] (property c actions)) no-actions properties))

(defn group-items
  "The items the group holds: the first chunk's, or every chunk's with `:all-open`."
  [{:keys [chunks]} mode]
  (vec (mapcat :items (if (= mode :all-open) chunks (take 1 chunks)))))

(defn for-plan
  "The actions for a `plan`: the group holds its first chunk, or with the
  `:all-open` mode every chunk, closing nothing."
  [plan mode tabs]
  (reconcile {:items (group-items plan mode) :tabs tabs :close? (not= mode :all-open)}))

(defn applescript-string [s]
  (str "\"" (-> s (str/replace "\\" "\\\\") (str/replace "\"" "\\\"")) "\""))

(defn background-script
  "AppleScript that starts an update in `app`'s window `window-id`, the
  window the browser check found. With `:park`, it first appends a new tab
  and makes it the window's active tab, and returns that tab's id. It then
  re-points the `:repoint` tabs in the background, finding every tab by
  the URL it shows before changing any, so a re-point can't make a later
  lookup find the wrong tab. Nil when there is nothing to do."
  [app window-id {:keys [park repoint]}]
  (let [steps (map (fn [{:keys [from url]}] [from (str "set URL to " (applescript-string url))]) repoint)]
    (when (or park (seq steps))
      (str/join "\n"
                (concat
                 [(str "tell application " (applescript-string app))
                  (str "  set w to window id " window-id)]
                 (when park
                   ["  set parked to make new tab at end of tabs of w"
                    "  set active tab index of w to (count of tabs of w)"])
                 (when (seq steps)
                   (concat
                    ["  set found to {}"
                     (str "  repeat with u in {" (str/join ", " (map (comp applescript-string first) steps)) "}")
                     "    set hit to missing value"
                     "    repeat with c in tabs of w"
                     "      if URL of c is (contents of u) then"
                     "        set hit to id of c"
                     "        exit repeat"
                     "      end if"
                     "    end repeat"
                     "    set end of found to hit"
                     "  end repeat"]
                    (map-indexed (fn [i [_ action]]
                                   (str "  if item " (inc i) " of found is not missing value then"
                                        " tell (tab id (item " (inc i) " of found) of w) to " action))
                                 steps)))
                 (when park ["  return id of parked"])
                 ["end tell"])))))

(defn focus-script
  "AppleScript that lands an update: it makes the tab showing `url` the
  active tab of window `window-id` of `app`, the window the browser check
  found, then closes the `parked` tab, if any. It never raises the window
  or the app, so the review queue never takes focus."
  ([app window-id url] (focus-script app window-id url nil))
  ([app window-id url parked]
   (str/join "\n"
             (concat
              [(str "tell application " (applescript-string app))
               (str "  set w to window id " window-id)
               "  set i to 0"
               "  repeat with t in tabs of w"
               "    set i to i + 1"
               (str "    if URL of t is " (applescript-string url) " then")
               "      set active tab index of w to i"
               "      exit repeat"
               "    end if"
               "  end repeat"]
              (when parked
                ["  try"
                 (str "    close tab id " parked " of w")
                 "  end try"])
              ["end tell"]))))
