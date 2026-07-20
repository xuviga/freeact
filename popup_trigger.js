(function() {
    var g = window.google;
    if (!g || !g.accounts) return 'GSI gone';
    var c = g.accounts.oauth2.initCodeClient({
        client_id: '990339570472-k6nqn1tpmitg8pui82bfaun3jrpmiuhs.apps.googleusercontent.com',
        scope: 'openid email profile',
        ux_mode: 'popup',
        callback: function(r) { window.__popup_code = r; }
    });
    c.requestCode();
    return 'popup requested';
})()
