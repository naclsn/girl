/*-*/;(function(){

const notifs = document.getElementById("notifs");

const notif_socket = new WebSocket('ws://localhost:8090/notif');
//notif_socket.onopen = e => console.log(e);
//notif_socket.onclose = e => console.warn(e);
//notif_socket.onerror = e => console.error(e);
notif_socket.onmessage = e => push_notif(JSON.parse(e.data));

/** @typedef {{id: string, runid: str, date: Date}} Notif */
/** @type {Notif[]} */
const notif_list = [];
function push_notif({id, runid, ts}) {
    const date = new Date(ts * 1000);
    notif_list.push({id, runid, date});
    const el = notifs.appendChild(document.createElement('li'));
    el.classList.add(String(id).replace(/[^-0-9A-Z_a-z]/g, '-'));
    el.innerHTML = `<button>${date.toLocaleString()} <sub>${runid}</sub></button>`;
}

})();
