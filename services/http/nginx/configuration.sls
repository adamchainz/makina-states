include:
  - makina-states.services.http.nginx.hooks
  - makina-states.services.http.nginx.services
  - makina-states.services.http.nginx.vhosts
{% set settings = salt['mc_nginx.settings']() %}
nginx-vhost-dirs:
  file.directory:
    - names:
      - {{settings.logdir}}
      - {{settings.basedir}}/conf.d
      - {{settings.basedir}}/sites-available
      - {{settings.basedir}}/sites-enabled
    - mode: 755
    - makedirs: true
    - watch_in:
      - mc_proxy: nginx-pre-conf-hook
    - watch_in:
      - mc_proxy: nginx-post-conf-hook

{% set modes = {
  '/etc/init.d/nginx-naxsi-ui': 755,
} %}

{% set sdata =salt['mc_utils.json_dump'](settings)  %}
{% for f in [
    '/etc/logrotate.d/nginx',
    '/usr/share/nginx-naxsi-ui/naxsi-ui/nx_extract.py',
    '/etc/init.d/nginx-naxsi-ui',
    '/etc/default/nginx-naxsi-ui',
    settings['basedir'] + '/fastcgi_params',
    settings['basedir'] + '/koi-utf',
    settings['basedir'] + '/koi-win',
    settings['basedir'] + '/mime.types',
    settings['basedir'] + '/naxsi.conf',
    settings['basedir'] + '/naxsi_core.rules',
    settings['basedir'] + '/nginx.conf',
    settings['basedir'] + '/naxsi-ui.conf',
    settings['basedir'] + '/proxy_params',
    settings['basedir'] + '/scgi_params',
    settings['basedir'] + '/uwsgi_params',
    settings['basedir'] + '/win-utf',
    '/etc/default/nginx',
] %}
makina-nginx-minimal-{{f}}:
  file.managed:
    - name: {{f}}
    - source: salt://makina-states/files/{{f}}
    - template: jinja
    - defaults:
      data: |
            {{sdata}}
    - user: root
    - group: root
    - makedirs: true
    - mode: {{modes.get(f, 644)}}
    - template: jinja
    - watch_in:
      - mc_proxy: nginx-pre-conf-hook
    - watch_in:
      - mc_proxy: nginx-post-conf-hook
{% endfor %}





