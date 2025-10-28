/*-*/; onload = async function() {
    'use strict';
    const {
        subpath: SUBPATH,
        basic_auth_passwd: BASIC_AUTH_PASSWD,
        query_default_backrange: QUERY_DEFAULT_BACKRANGE,
        notif_limit: NOTIF_LIMIT,
        app_name: APP_NAME,
    } = await fetch('-/sitelocal.json').then(r => r.json());

    function passwordRequired() {
        if (!BASIC_AUTH_PASSWD) return '';
        return passwordRequired._credentials
            || (passwordRequired._credentials = btoa(`:${prompt("babasdfbsa")}`));
    }
    passwordRequired._credentials = null;

    if (APP_NAME.length)
        document.title = `${APP_NAME} - ${document.title}`;

    /** @param {string} txt */
    function stableRandomColor(txt) {
        const hash = txt.split("").reduce((acc, cur) => ((acc << 5) - acc + cur.charCodeAt(0)) | 0, 0);
        return 'hsl(' + hash % 360 + ', 80%, 50%)';
    }

    /**
     * @param {RequestInfo | URL} input
     * @param {RequestInit | null | undefined} init
     */
    async function cacheFetchJSON(input, init) {
        const cacheKey = 'string' !== typeof input && 'url' in input ? input.url : '' + input;
        const has = cacheFetchJSON.cache.get(cacheKey);
        if (has) return has;
        const r = await fetch(input, init).then(r => r.json())
        cacheFetchJSON.cache.set(r);
        return r;
    }
    cacheFetchJSON.cache = new Map;

    /** @typedef {{id: string, runid: str, date: Date, tags: string[]}} Notif */

    class NotifListCE extends HTMLElement {
        static tag = 'notif-list';
        static template = document.getElementById(NotifListCE.tag);

        /** @type {TagComboBoxCE} */ tags;
        /** @type {HTMLButtonElement} */ force_search;
        /** @type {HTMLInputElement} */ min_date;
        /** @type {HTMLInputElement} */ max_date;
        /** @type {HTMLDivElement} */ list;
        /** @type {WebSocket} */ socket;

        constructor() {
            super();
            this.attachShadow({ mode: 'open' }).appendChild(NotifListCE.template.content.cloneNode(true));

            this.tags = this.shadowRoot.getElementById('tags');
            this.force_search = this.shadowRoot.getElementById('force-search');
            this.min_date = this.shadowRoot.getElementById('min-date');
            this.max_date = this.shadowRoot.getElementById('max-date');
            this.list = this.shadowRoot.getElementById('list');

            this.socket = new WebSocket(`${'https:' === location.protocol ? 'wss:' : 'ws:'}//${location.host}${SUBPATH}/-/notif`);
            const hold_notifs_until_old_fetched = [];
            this.socket.onopen = _ => this._attempts = 0;
            this.socket.onclose = e => 1000 === e.code || this.socketReconnect(e.code);
            this.socket.onerror = e => console.error(e);
            this.socket.onmessage = e => hold_notifs_until_old_fetched.push(JSON.parse(e.data));

            const now = Date.now() / 1000;
            fetch(`-/api/events?min_ts=${now - QUERY_DEFAULT_BACKRANGE}&max_ts=${now}`)
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

            this.tags.onchange = _ => {
                for (const it of this.list.children)
                    it.style.display = this._activeFilter(it.notif) ? '' : 'none';
            };
            this.force_search.onclick = this.forceSearch.bind(this);
        }

        _attempts = 0;
        socketReconnect() {
            if (this._attempts++ < 5) {
                console.warn("ws dc, re in 10s: " + this._attempts);
                setTimeout(() => {
                    const niw = new WebSocket(this.socket.url);
                    niw.onopen = this.socket.onopen;
                    niw.onclose = this.socket.onclose;
                    niw.onerror = this.socket.onerror;
                    niw.onmessage = this.socket.onmessage;
                    this.socket.onopen = this.socket.onclose = this.socket.onerror = this.socket.onmessage = null;
                    this.socket = niw;
                }, 10000);
            } else console.error("could not reconnect");
        }

        /** @param {Notif} notif */
        _activeFilter(notif) {
            // matches if: no `any_tag` filter, or any notif.tag in the set
            const matches = !this.tags.current_tags.size
                || notif.tags.some(this.tags.current_tags.has.bind(this.tags.current_tags));
            return matches;
        }

        pushNotif({ id, runid, ts, tags }) {
            this.tags.updateAllTags(tags);
            /** @type {NotifListItemCE} */
            const it = document.createElement(NotifListItemCE.tag);
            it.setNotif({ id, runid, date: new Date(ts * 1000), tags });
            it.style.display = this._activeFilter(it.notif) ? '' : 'none';
            this.list.prepend(it);
            if (NOTIF_LIMIT < this.list.childElementCount)
                this.list.lastElementChild.remove();
        }

        forceSearch() {
            const url = new URL(`${location.origin}${SUBPATH}/-/api/events`);
            const now = Date.now() / 1000;
            url.searchParams.append('min_ts', this.min_date.valueAsDate / 1000 || now - QUERY_DEFAULT_BACKRANGE);
            url.searchParams.append('max_ts', this.max_date.valueAsDate / 1000 || now);
            for (const tag of this.tags.current_tags) url.searchParams.append('any_tag', tag);

            fetch(url)
                .then(r => r.json())
                .then(r => console.dir(r)); // TODO
        }
    }

    class TagPillCE extends HTMLElement {
        static tag = 'tag-pill';
        static template = document.getElementById(TagPillCE.tag);

        /** @type {string} */ tag;

        constructor() {
            super();
            this.attachShadow({ mode: 'open' }).appendChild(TagPillCE.template.content.cloneNode(true));
        }

        /** @param {string} tag */
        setTag(tag) {
            this.tag = tag;
            this.style.setProperty('--tag', stableRandomColor(tag));
            this.shadowRoot.append(tag);
            /** @type {NotifListCE} */
            const feed = document.getElementById('feed');
            this.onclick = e => {
                e.stopPropagation();
                feed.tags.toggleTag(tag);
            };
        }
    }

    class TagComboBoxCE extends HTMLElement {
        static tag = 'tag-combo-box';
        static template = document.getElementById(TagComboBoxCE.tag);

        /** @type {HTMLInputElement} */ text;
        /** @type {HTMLDataListElement} */ datalist;
        /** @type {Set<string>} */ current_tags = new Set;
        /** @type {Set<string>} */ all_known_tags = new Set;

        constructor() {
            super();
            this.attachShadow({ mode: 'open' }).appendChild(TagComboBoxCE.template.content.cloneNode(true));

            this.text = this.shadowRoot.getElementById('text');
            this.datalist = this.shadowRoot.getElementById('known-list');

            this.text.onfocus = _ => fetch('-/api/tags')
                .then(r => r.json())
                .then(r => { this.text.onfocus = null; this.updateAllTags(r); });
            this.text.parentElement.onclick = _ => this.text.focus();
            this.text.parentElement.onsubmit = e => {
                e.preventDefault();
                this.addTag(this.text.value);
                this.text.value = "";
            };
            this.text.onkeydown = e => {
                if ('Backspace' === e.key && !this.text.value.length && this.current_tags.size)
                    this.deleteTag(this.text.previousElementSibling.tag);
            };
            this.text.oninput = _ => this.text.style.width = this.text.value.length + 'ch';
        }

        /** @param {string} tag */
        addTag(tag) {
            tag = tag.trim();
            if (!tag.length || this.current_tags.has(tag)) return;
            this.current_tags.add(tag);

            const pill = document.createElement(TagPillCE.tag);
            pill.setTag(tag);
            this.text.before(pill);
            this.dispatchEvent(new Event('change'));
        }

        /** @param {string} tag */
        deleteTag(tag) {
            if (!this.current_tags.has(tag)) return;
            this.current_tags.delete(tag);
            /** @type {TagPillCE} */
            let e = this.text;
            while ((e = e.previousElementSibling) && tag !== e.tag);
            e.remove();
            this.dispatchEvent(new Event('change'));
        }

        /** @param {string} tag */
        toggleTag(tag) {
            this.current_tags.has(tag) ? this.deleteTag(tag) : this.addTag(tag);
        }

        /** @param {string[]} add_tags */
        updateAllTags(add_tags) {
            let hasnew = !this.all_known_tags.size;
            for (const tag of add_tags) {
                hasnew = hasnew || this.all_known_tags.has(tag);
                this.all_known_tags.add(tag);
            }
            if (hasnew) {
                this.datalist.innerHTML = '';
                for (const tag of this.all_known_tags)
                    this.datalist.appendChild(document.createElement('option')).value = tag;
            }
        }
    }

    class NotifListItemCE extends HTMLElement {
        static tag = 'notif-list-item';
        static template = document.getElementById(NotifListItemCE.tag);

        /** @type {Notif} */ notif;
        /** @type {HTMLElement} */ date;
        /** @type {HTMLElement} */ e_id;
        /** @type {HTMLElement} */ tags;

        constructor() {
            super();
            this.attachShadow({ mode: 'open' }).appendChild(NotifListItemCE.template.content.cloneNode(true));

            this.date = this.shadowRoot.getElementById('date');
            this.e_id = this.shadowRoot.getElementById('id');
            this.tags = this.shadowRoot.getElementById('tags');

            this.onclick = this.notifClicked.bind(this);
        }

        /** @param {Notif} notif */
        setNotif(notif) {
            this.notif = notif;
            this.title = notif.runid;

            this.style.setProperty('--runid', stableRandomColor(notif.runid));
            this.date.textContent = notif.date.toLocaleString();
            this.e_id.textContent = notif.id;

            for (const tag of notif.tags)
                this.tags.appendChild(document.createElement(TagPillCE.tag)).setTag(tag);
        }

        notifClicked() {
            const already = document.getElementById(`details--${this.notif.runid}`);
            if (already) return void already.remove();

            /** @type {NotifDetailsCE} */
            const det = document.createElement(NotifDetailsCE.tag);
            det.setSourceNotifItem(this);
            this.classList.add('selected');

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
                .onclick = this.remove.bind(this);

            this.runid = this.shadowRoot.getElementById('runid');
            this.tags = this.shadowRoot.getElementById('tags');
            this.data = this.shadowRoot.getElementById('data');

            this.data.ontoggle = _ => this._fetch_right_away = true;
        }

        remove() {
            this.source.classList.remove('selected');
            super.remove();
        }

        _fetch_right_away = false;
        _fetchData() {
            const pontoggle = this.data.ontoggle;
            this.data.ontoggle = null;
            cacheFetchJSON(
                `${SUBPATH}/-/api/data?runid=${this.source.notif.runid}`,
                { headers: { 'Authorization': `Basic ${passwordRequired()}` } })
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
                    }))
                .catch(err => {
                    passwordRequired._credentials = null;
                    alert(`${err} lol`);
                    this.data.removeAttribute('open');
                    setTimeout(_ => this.data.ontoggle = pontoggle, 1000);
                });
        }

        /** @param {NotifListItemCE} it */
        setSourceNotifItem(it) {
            this.id = `details--${it.notif.runid}`;

            this.source = it;
            this.style.setProperty('--runid', stableRandomColor(it.notif.runid));

            this.runid.textContent = it.notif.runid;
            for (const tag of it.notif.tags)
                this.tags.appendChild(document.createElement(TagPillCE.tag)).setTag(tag);

            // if *somehow* it was toggled before `setSourceNotifItem`
            if (this._fetch_right_away) this._fetchData();
            else this.data.ontoggle = this._fetchData.bind(this);
        }
    }

    customElements.define(NotifListCE.tag, NotifListCE);
    customElements.define(TagPillCE.tag, TagPillCE);
    customElements.define(TagComboBoxCE.tag, TagComboBoxCE);
    customElements.define(NotifListItemCE.tag, NotifListItemCE);
    customElements.define(NotifDetailsCE.tag, NotifDetailsCE);

    // XXX: slap-meta
    onkeydown = e => {
        if (e.ctrlKey && 'k' === e.key) {
            e.preventDefault();
            document.body.firstElementChild.shadowRoot.getElementById('tags').shadowRoot.getElementById('text').focus();
        }
    };
};
