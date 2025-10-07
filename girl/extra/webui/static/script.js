/*-*/; onload = function() {
    'use strict';
    const SUBPATH = '/webui'; // XXX: but, this is set by user code tho...
    /**
     * by default, queries go [now-that .. now]; this includes:
     *  - the initial query at page load
     *  - force searches with no given min_ts
     */
    const QUERY_DEFAULT_BACKIDK = 60 * 60 * 24; // XXX: may also be site dependent

    /** @param {string} txt */
    function stableRandomColor(txt) {
        const hash = txt.split("").reduce((acc, cur) => ((acc << 5) - acc + cur.charCodeAt(0)) | 0, 0);
        return 'hsl(' + hash % 360 + ', 80%, 50%)';
    }

    /**
     * @param {RequestInfo | URL} input
     * @param {RequestInit | null | undefined} init
     */
    function cacheFetchJSON(input, init) {
        const cacheKey = 'url' in input ? input.url : '' + input;
        const has = cacheFetchJSON.cache.get(cacheKey);
        if (has) return new Promise(res => res(has));
        return fetch(input, init)
            .then(r => r.json())
            .then(r => { cacheFetchJSON.cache.set(r); return r; })
    }
    cacheFetchJSON.cache = new Map;

    /** @typedef {{id: string, runid: str, date: Date, tags: string[]}} Notif */

    class NotifListCE extends HTMLElement {
        static tag = 'notif-list';
        static template = document.getElementById(NotifListCE.tag);

        /** @type {HTMLInputElement} */ tags;
        /** @type {HTMLButtonElement} */ force_search;
        /** @type {HTMLInputElement} */ min_date;
        /** @type {HTMLInputElement} */ max_date;
        /** @type {HTMLOListElement} */ list;
        /** @type {WebSocket} */ socket;

        constructor() {
            super();
            this.attachShadow({ mode: 'open' }).appendChild(NotifListCE.template.content.cloneNode(true));

            this.tags = this.shadowRoot.getElementById('tags');
            this.force_search = this.shadowRoot.getElementById('force-search');
            this.min_date = this.shadowRoot.getElementById('min-date');
            this.max_date = this.shadowRoot.getElementById('max-date');
            this.list = this.shadowRoot.getElementById('list');

            this.socket = new WebSocket(`ws://${location.host}${SUBPATH}/-/notif`);
            const hold_notifs_until_old_fetched = [];
            this.socket.onopen = this.socketOpened.bind(this);
            this.socket.onclose = this.socketClosed.bind(this);
            this.socket.onerror = this.socketError.bind(this);
            this.socket.onmessage = e => hold_notifs_until_old_fetched.push(JSON.parse(e.data));

            const now = Date.now() / 1000;
            fetch(`${SUBPATH}/-/api/events?min_ts=${now - QUERY_DEFAULT_BACKIDK}&max_ts=${now}`)
                .then(r => r.json())
                .then(/** @param {{[id: string]: any[]}} r */ r => {
                    const push = this.pushNotif.bind(this);
                    Object
                        .entries(r)
                        .flatMap(([id, runs]) => runs.map(run => ({ id, ...run })))
                        .sort((a, b) => a.ts - b.ts)
                        .forEach(push);
                    hold_notifs_until_old_fetched.forEach(push);
                    hold_notifs_until_old_fetched.length = 0;
                    this.socket.onmessage = e => push(JSON.parse(e.data));
                });

            this.tags.oninput = this.tagsInput.bind(this);
            this.force_search.onclick = this.forceSearch.bind(this);
        }

        socketOpened() { }
        socketClosed() { console.warn("socket closed - TODO: attempt reconnect?"); }
        socketError(err) { console.error(err); }

        /** @type {Set<string>} */ all_known_tags = new Set; // TODO: completion/neater tag search
        /** @type {Set<string>?} */ _active_filter_tags = null;
        /** @param {Notif} notif */
        _activeFilter(notif) {
            if (!this._active_filter_tags) {
                const val = this.tags.value.trim();
                this._active_filter_tags = new Set(val.length ? val.split(/\s*,\s*/) : []);
            }
            // matches if: no `any_tag` filter, or any notif.tag in the set
            const matches = !this._active_filter_tags.size
                || notif.tags.some(this._active_filter_tags.has.bind(this._active_filter_tags));
            return matches;
        }

        pushNotif({ id, runid, ts, tags }) {
            tags.forEach(this.all_known_tags.add.bind(this.all_known_tags));
            /** @type {NotifListItemCE} */
            const it = document.createElement(NotifListItemCE.tag);
            it.setNotif({ id, runid, date: new Date(ts * 1000), tags });
            const li = document.createElement('li');
            li.appendChild(it);
            this.list.prepend(li);
            li.style.display = this._activeFilter(it.notif) ? '' : 'none';
        }

        tagsInput() {
            this._active_filter_tags = null; // invalidate old set
            for (const li of this.list.children)
                li.style.display = this._activeFilter(li.firstChild.notif) ? '' : 'none';
        }

        forceSearch() {
            const url = new URL(`${location.origin}${SUBPATH}/-/api/events`);
            const now = Date.now() / 1000;
            url.searchParams.append('min_ts', this.min_date.valueAsDate / 1000 || now - QUERY_DEFAULT_BACKIDK);
            url.searchParams.append('max_ts', this.max_date.valueAsDate / 1000 || now);
            for (const tag of this.tags.value.trim().split(/\s*,\s*/))
                if (tag) url.searchParams.append('any_tag', tag);

            fetch(url)
                .then(r => r.json())
                .then(r => console.dir(r)); // TODO
        }
    }

    class NotifListItemCE extends HTMLElement {
        static tag = 'notif-list-item';
        //static template = document.getElementById(NotifListItemCE.tag); // TODO

        /** @type {Notif} */ notif;

        constructor() {
            super();
            this.attachShadow({ mode: 'open' }); //.appendChild(NotifListItemCE.template.content.cloneNode(true));
        }

        /** @param {Notif} notif */
        setNotif(notif) {
            this.notif = notif;
            //this.classList.add(notif.id.replace(/[^-0-9A-Z_a-z]/g, '-'));
            const but = this.shadowRoot.appendChild(document.createElement('button'));
            but.title = notif.runid;
            but.innerHTML = `${notif.date.toLocaleString()} <sup>${notif.id}</sup>`;
            but.onclick = this.notifClicked.bind(this);
        }

        notifClicked() {
            const already = document.getElementById(`details--${this.notif.runid}`);
            if (already) return void already.removeMe();
            const det = document.createElement(NotifDetailsCE.tag);
            det.setSourceNotifItem(this);
            for (const sib of document.getElementById('main').children)
                if (sib.source.notif.date < this.notif.date)
                    return void sib.before(det);
            document.getElementById('main').appendChild(det);
        }
    }

    class NotifDetailsCE extends HTMLElement {
        static tag = 'notif-details';
        static template = document.getElementById(NotifDetailsCE.tag);

        /** @type {NotifListItemCE} */ source;
        /** @type {HTMLElement} */ runid;
        /** @type {HTMLDivElement} */ tags;
        /** @type {HTMLDetailElement} */ data;

        constructor() {
            super();
            this.attachShadow({ mode: 'open' }).appendChild(NotifDetailsCE.template.content.cloneNode(true));

            this.shadowRoot
                .getElementById('x')
                .onclick = this.removeMe.bind(this);

            this.runid = this.shadowRoot.getElementById('runid');
            this.tags = this.shadowRoot.getElementById('tags');
            this.data = this.shadowRoot.getElementById('data');

            this.data.ontoggle = _ => this._fetch_right_away = true;
        }

        removeMe() {
            this.source.shadowRoot.firstChild.style.background = '';
            this.remove();
        }

        _fetch_right_away = false;
        _fetchData() {
            this.data.ontoggle = null;
            cacheFetchJSON(`${SUBPATH}/-/api/data?runid=${this.source.notif.runid}`)
                .then(({ data }) => data
                    .forEach(({ key, ts, data }) => {
                        const details = this.data.appendChild(document.createElement('details'));
                        try { data = JSON.stringify(JSON.parse(data), null, 4); } catch { }
                        details
                            .appendChild(document.createElement('summary'))
                            .textContent = `${new Date(ts * 1000).toLocaleString()}: ${key}`;
                        details
                            .appendChild(document.createElement('pre'))
                            .textContent = data;
                    }));
        }

        /** @param {NotifListItemCE} it */
        setSourceNotifItem(it) {
            this.id = `details--${it.notif.runid}`;

            this.source = it;
            const bg = stableRandomColor(it.notif.runid);
            it.shadowRoot.firstChild.style.background = bg;
            this.data.style.background = bg;

            this.runid.textContent = it.notif.runid;
            for (const tag of it.notif.tags) {
                const pill = this.tags.appendChild(document.createElement('span'));
                pill.textContent = tag;
                pill.classList.add('tag');
                pill.style.setProperty('--c', stableRandomColor(tag));
            }

            if (this._fetch_right_away) this._fetchData();
            else this.data.ontoggle = this._fetchData.bind(this);
        }
    }

    customElements.define(NotifListCE.tag, NotifListCE);
    customElements.define(NotifListItemCE.tag, NotifListItemCE);
    customElements.define(NotifDetailsCE.tag, NotifDetailsCE);

};
