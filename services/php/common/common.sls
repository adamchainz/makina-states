{% set locs = salt['mc_locations.settings']() %}
{% set phpSettings = salt['mc_php.settings']()  %}
{% set s_ALL = phpSettings.s_all %}
{% import "makina-states/services/php/macros.sls" as macros with context %}

{#- Common php installations (mod_php or php-fpm) files #}
include:
  - makina-states.services.php.hooks
{%  if grains.get('lsb_distrib_id','') == "Debian" -%}
  {# Include dotdeb repository for Debian #}
  - makina-states.localsettings.repository_dotdeb

dotdeb-apache-makina-apache-php-pre-inst:
  mc_proxy.hook:
    - require:
      - pkgrepo: dotdeb-repo
    - watch_in:
      - mc_proxy: makina-php-pre-inst
{%endif %}

php-cli:
  pkg.installed:
    - pkgs:
      - php5-cli
    - watch:
      - mc_proxy: makina-php-pre-inst
    - watch_in:
      - mc_proxy: makina-php-post-inst
makina-php-timezone:
  file.managed:
    - user: root
    - group: root
    - makedirs: true
    - mode: 664
    - name: {{ phpSettings.confdir }}/timezone.ini
    - source: salt://makina-states/files{{ phpSettings.confdir }}/timezone.ini
    - template: 'jinja'
    - defaults:
        timezone: "{{ phpSettings.timezone }}"
    - require:
      - mc_proxy: makina-php-post-inst
    - watch_in:
      - mc_proxy: makina-php-pre-conf

makina-php-composer:
  file.managed:
    - user: root
    - group: root
    - mode: 755
    - name: /usr/local/bin/composer
    - source: '{{phpSettings.composer}}'
    - source_hash: 'sha1={{phpSettings.composer_sha1}}'
    - require:
      - mc_proxy: makina-php-post-inst
    - watch_in:
      - mc_proxy: makina-php-pre-conf

{{ macros.toggle_ext('xdebug', phpSettings.xdebug_install and phpSettings.xdebug_enabled) }}

#--------------------- APC (mostly deprecated)
{% if phpSettings.apc_install %}
makina-php-apc:
  file.managed:
    - user: root
    - makedirs: true
    - group: root
    - mode: 664
    - name: {{ phpSettings.confdir }}/apcu.ini
    - source: salt://makina-states/files{{ phpSettings.confdir }}/apcu.ini
    - template: 'jinja'
    - defaults:
        enabled: {{ phpSettings.apc_enabled }}
        enable_cli: {{ phpSettings.apc_enable_cli }}
        shm_segments: "{{ phpSettings.apc_shm_segments }}"
        shm_size: "{{ phpSettings.apc_shm_size }}"
        mmap_file_mask: "{{ phpSettings.apc_mmap_file_mask }}"
    - require:
      - mc_proxy: makina-php-post-inst
    - watch_in:
      - mc_proxy: makina-php-pre-conf

{% if not ( (grains['os'] in 'Ubuntu') and (salt['mc_pkgs.settings']().udist not in ['precise'])) %}
{{ macros.toggle_ext('apcu', apc_enabled)}}
{% endif %}
{% endif %}
