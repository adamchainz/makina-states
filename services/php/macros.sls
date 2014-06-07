{# PHP specific macros
#
# * pool => create all states for a fpm php pool
#
#   - domain
#       domain name (main project domain name aka ServerName or site name)
#   - pool_name
#       domain nickname, used in states and log files and of course pool name,
#       if not given it will be build from domain name
#   - pool_template_sourcel:
#       defaults to makina-states's one, jinja template to construct the fpm pool configuration from
#   - settings
#       default data dictionnary to be merge with mc_php.settings one if you
#       want to customize php parameters
#   - open_basedir_additions:
#       directories to add to openbasedirs
#   - include_path_additions
#       directories to add to include directories
#   - custom_listen
#       Custom listen string for php fpm listen directive
#   - chroot
#       Do we run in a fpm chrooted env. (certainly defaults to true in current layout)
#   - extra_jinja_pool_variables
#       extra variables to load for fpmpool templates rendering
#   - nice_priority
#       Nice value for the fpm pool
#   - use_shared_socket_path
#       Do we use the fpm shared socket path (multiple projects share the same pool)
#   - session_cookie_domain
#       Special cookie domain string for cookies (totally optionnal)
#   - pool_template_source
#       default pool_template_source jinja file to generate the fpm pool from
#   - pool_name
#       force the fpm pool name (useful for multiple projects to use the same pool)
#   - project_root
#       top level project directory
#       (totally optionnal if you use the predefined layout)
#   - doc_root
#        absolute path to a custom directory
#        (totally optionnal if you use the predefined layout)
#   - relative_document_root
#       name of the document root subdirectory
#       (totally optionnal if you use the predefined layout)
#
#  In most case:
#     - Only the "domain" parameter will be sufficient if you follow the makina-states layout:
#     - We use a fpm pool per project
#
#   /var/log <- fpm logs dir
#   /var/tmp <- fpm tmp dir
#   /src/projects/myproject-com/project
#                                 \_ www          <- doc_root
#                                 \_ var/tmp      <- tmp files
#                                 \_ var/private  <- private dir
#                                 \_ var/log      <- logs (fpm ppol)
#                                 \_ var/fcgi     <- socket(s) path
#
#}

{% set ugs = salt['mc_usergroup.settings']() %}
{% set apacheData = salt['mc_apache.settings']() %}
{% set nodetypes = salt['mc_nodetypes.registry']() %}
{% set phpData = salt['mc_php.settings']() %}
{% set locs = salt['mc_locations.settings']() %}
{% set default_pool_template_source = (
    'salt://makina-states/files/etc/php5/fpm/pool.d/pool.conf'
   ) %}

{% macro includes() %}
  - makina-states.services.php.phpfpm_with_apache
{% endmacro %}

{% macro fpm_pool(domain,
                  settings=None,
                  open_basedir_additions='',
                  include_path_additions='',
                  custom_listen=None,
                  chroot=None,
                  nice_priority=-19,
                  use_shared_socket_path=False,
                  session_cookie_domain=None,
                  pool_template_source=default_pool_template_source,
                  pool_name=None,
                  project_root=None,
                  doc_root=None,
                  extra_jinja_pool_variables=None,
                  socket_name=None,
                  relative_document_root='www',
                  project=None,
                  includes=False) -%}
{% set phpData = salt['mc_php.settings']() %}
{% if not extra_jinja_pool_variables %}
{%  set extra_jinja_pool_variables = {} %}
{% endif %}
{% set doc_root = salt['mc_project.doc_root'](doc_root=doc_root,
                                              domain=domain,
                                              project_root=project_root,
                                              project=project) %}
{% set project = salt['mc_project.gen_id'](project or domain) %}
{% set pool_name = pool_name or project %}
{% set project_root = project_root or '{0}/{1}/project'.format(locs.projects_dir, project) %}

{% if chroot %}
{%   if not doc_root.startswith(project_root) %}
{%      set chroot = False %}
{%    endif %}
{% endif %}

{% if not session_cookie_domain %}
{%    set session_cookie_domain = domain %}
{% endif %}

{# Merge settings with phpData, @see mc_states.mc_php.settings for settings tree #}
{% if settings != None %}
{%   set phpData = salt['mc_utils.dictupdate'](phpData.copy(), settings) %}
{% endif %}

{% if chroot %}
{%   set project_root = '' %}
{% endif %}

{% set mode='production' %}
{% if salt['mc_nodetypes.registry']()['is']['devhost'] %}
{%  set mode='dev' %}
{% endif %}

{% set doc_root    = '{0}/{1}'.format(project_root, phpData.fpm.relative_document_root) %}
{% set tmp_dir     = '{0}/{1}'.format(project_root, phpData.fpm.tmp_relative_path) %}
{% set log_dir     = '{0}/{1}'.format(project_root, phpData.fpm.log_relative_path) %}
{# {% set sock_dir    = '{0}/{1}'.format(project_root, phpData.fpm.socket_relative_path) %} #}
{% set sock_dir    = apacheData.fastcgi_socket_directory %}
{% if not socket_name %}
{% set socket_name   = salt['mc_php.get_fpm_socket_name'](project) %}
{% endif %}
{% set private_dir = '{0}/{1}'.format(project_root, phpData.fpm.private_relative_path) %}

{% if includes %}
includes:
{{includes()}}
{% endif %}

# Pool file
makina-php-pool-{{ pool_name }}:
  file.managed:
    - user: root
    - group: root
    - mode: 664
    - name: {{ phpData.etcdir }}/fpm/pool.d/{{ pool_name }}.conf
    - source: {{ pool_template_source }}
    - template: 'jinja'
    - defaults:
        domain: "{{ domain }}"
        pool_name: "{{ pool_name }}"
        pool_root: "{{ project_root }}"
        pool_doc_root: "{{ doc_root }}"
        pool_tmp_dir: "{{ tmp_dir }}"
        pool_log_dir: "{{ log_dir }}"
        pool_sock_dir: "{{ sock_dir }}"
        pool_private_dir: "{{ private_dir }}"
        var_tmp: "{{ locs.var_tmp_dir }}"
        var_log: "{{ locs.var_log_dir }}"
        chroot: {{ phpData.fpm.chroot }}
        use_socket: {{ phpData.fpm.use_socket }}
        socket_name: "{{ socket_name }}"
        use_shared_socket_path: {{ use_shared_socket_path|int(0) }}
        fpm_sockets_dir: "{{ phpData.fpm_sockets_dir }}"
        custom_listen: "{{ custom_listen }}"
        listen_backlog: {{ phpData.fpm.listen_backlog }}
        listen_allowed_clients: "{{ phpData.fpm.listen_allowed_clients }}"
        phpuser: "{{ phpData.fpm.phpuser }}"
        phpgroup: "{{ phpData.fpm.phpgroup }}"
        listen_mod: "{{ phpData.fpm.listen_mod }}"
        pool_nice_priority: {{ nice_priority }}
        pm_max_requests: {{ phpData.fpm.pm.max_requests }}
        pm_max_children: {{ phpData.fpm.pm.max_children }}
        pm_start_servers: {{ phpData.fpm.pm.start_servers }}
        pm_min_spare_servers: {{ phpData.fpm.pm.min_spare_servers }}
        pm_max_spare_servers: {{ phpData.fpm.pm.max_spare_servers }}
        statuspath: "{{ phpData.fpm.statuspath }}"
        ping: "{{ phpData.fpm.ping }}"
        pong: "{{ phpData.fpm.pong }}"
        request_terminate_timeout: "{{ phpData.fpm.request_terminate_timeout }}"
        request_slowlog_timeout: "{{ phpData.fpm.request_slowlog_timeout }}"
        session_auto_start: {{ phpData.session_auto_start|int(0) }}
        session_gc_maxlifetime: {{ phpData.session.gc_maxlifetime }}
        session_gc_probability: {{ phpData.session.gc_probability }}
        session_gc_divisor: {{ phpData.session.gc_divisor }}
        session_cookie_domain: {{ session_cookie_domain }}
        custom_sessions: {{ phpData.custom_sessions.enabled }}
        session_save_path: "{{ phpData.custom_sessions.save_path }}"
        session_save_handler: "{{ phpData.custom_sessions.save_handler }}"
        open_basedir: {{ phpData.open_basedir|int(1) }}
        open_basedir_additions: "{{ open_basedir_additions }}"
        include_path_additions: "{{ include_path_additions }}"
        file_uploads: {{ phpData.file_uploads|int(1) }}
        upload_max_filesize: "{{ phpData.upload_max_filesize }}"
        max_input_vars: {{ phpData.max_input_vars }}
        max_input_time: {{ phpData.max_input_time }}
        display_errors: {{ phpData.display_errors|int(0) }}
        error_reporting: {{ phpData.error_reporting }}
        memory_limit: "{{ phpData.memory_limit }}"
        max_execution_time: "{{ phpData.max_execution_time }}"
        allow_url_fopen: {{ phpData.allow_url_fopen|int(0) }}
        opcache_install: {{ phpData.modules.opcache.install }}
        opcache_enabled: {{ phpData.modules.opcache.enabled|int(1) }}
        opcache_enable_cli: {{ phpData.modules.opcache.enable_cli|int(1) }}
        opcache_memory_consumption: {{ phpData.modules.opcache.memory_consumption|int(64) }}
        opcache_interned_strings_buffer: {{ phpData.modules.opcache.interned_strings_buffer|int(4) }}
        opcache_max_accelerated_files: {{ phpData.modules.opcache.max_accelerated_files|int(2000) }}
        opcache_max_wasted_percentage: {{ phpData.modules.opcache.max_wasted_percentage|int(5) }}
        opcache_use_cwd: {{ phpData.modules.opcache.use_cwd|int(1) }}
        opcache_validate_timestamps: {{ phpData.modules.opcache.validate_timestamps|int(1) }}
        opcache_revalidate_freq: {{ phpData.modules.opcache.revalidate_freq|int(2) }}
        opcache_revalidate_path: {{ phpData.modules.opcache.revalidate_path|int(0) }}
        opcache_save_comments: {{ phpData.modules.opcache.save_comments|int(0) }}
        opcache_load_comments: {{ phpData.modules.opcache.load_comments|int(0) }}
        opcache_fast_shutdown: {{ phpData.modules.opcache.fast_shutdown|int(0) }}
        opcache_enable_file_override: {{ phpData.modules.opcache.enable_file_override|int(1) }}
        opcache_optimization_level: {{ phpData.modules.opcache.optimization_level }}
        opcache_blacklist_filename: {{ phpData.modules.opcache.blacklist_filename }}
        opcache_max_file_size: {{ phpData.modules.opcache.max_file_size|int(0) }}
        opcache_force_restart_timeout: {{ phpData.modules.opcache.force_restart_timeout|int(180) }}
        opcache_error_log: {{ phpData.modules.opcache.error_log }}
        opcache_log_verbosity_level: {{ phpData.modules.opcache.log_verbosity_level|int(1) }}
        apc_install: {{ phpData.modules.apc.install }}
        apc_enabled: {{ phpData.modules.apc.enabled|int(0) }}
        apc_enable_cli: {{ phpData.modules.apc.enable_cli|int(0) }}
        apc_rfc1867: {{ phpData.modules.apc.rfc1867|int(0) }}
        apc_include_once_override: {{ phpData.modules.apc.include_once_override|int(1) }}
        apc_canonicalize: {{ phpData.modules.apc.canonicalize|int(1) }}
        apc_stat: {{ phpData.modules.apc.stat|int(1) }}
        apc_stat_ctime: {{ phpData.modules.apc.stat_ctime|int(0) }}
        apc_num_files_hint: "{{ phpData.modules.apc.num_files_hint }}"
        apc_user_entries_hint: "{{ phpData.modules.apc.user_entries_hint }}"
        apc_ttl: "{{ phpData.modules.apc.ttl }}"
        apc_user_ttl: "{{ phpData.modules.apc.user_ttl }}"
        apc_gc_ttl: "{{ phpData.modules.apc.gc_ttl }}"
        apc_filters: "{{ phpData.modules.apc.filters }}"
        apc_max_file_size: "{{ phpData.modules.apc.max_file_size }}"
        apc_write_lock: {{ phpData.modules.apc.write_lock|int(1) }}
        apc_file_update_protection: "{{ phpData.modules.apc.file_update_protection }}"
        apc_lazy_functions: "{{ phpData.modules.apc.lazy_functions }}"
        apc_lazy_classes: "{{ phpData.modules.apc.lazy_classes }}"
        xdebug_install: {{ phpData.modules.xdebug.install|int(0) }}
        xdebug_enabled: {{ phpData.modules.xdebug.enabled|int(0) }}
        xdebug_collect_params: {{ phpData.modules.xdebug.collect_params|int(0) }}
        xdebug_profiler_enable: {{ phpData.modules.xdebug.profiler_enable|int(0) }}
        xdebug_profiler_enable_trigger: {{ phpData.modules.xdebug.profiler_enable_trigger|int(0) }}
        xdebug_profiler_output_name: "{{ phpData.modules.xdebug.profiler_output_name }}"
        mode: {{mode}}
        extra: |
               {{salt['mc_utils.json_dump']( extra_jinja_pool_variables)}}
    - require:
      - mc_proxy: makina-php-post-inst
    - watch_in:
      - mc_proxy: makina-php-pre-restart

makina-php-pool-{{ pool_name }}-logrotate:
  file.managed:
    - name: "{{salt['mc_locations.settings']().conf_dir}}/logrotate.d/fpm.{{pool_name}}.conf"
    - source: salt://makina-states/files/etc/logrotate.d/fpmpool.conf
    - template: jinja
    - defaults:
        name: {{pool_name}}
        logdir: {{log_dir}}
        rotate: {{phpData.rotate}}
    - mode: 750
    - user: root
    - group: root
    - require:
      - mc_proxy: makina-php-post-inst
    - require_in:
      - mc_proxy: makina-php-pre-restart

makina-php-pool-{{ pool_name }}-directories:
  file.directory:
    - user: {{ phpData.fpm.phpuser }}
    - group: {{ugs.group }}
    - mode: "2775"
    - makedirs: True
    - names:
      - {{ private_dir }}
      - {{ tmp_dir }}
      - {{ log_dir }}
      - {{ doc_root }}
      {% if phpData.fpm.use_socket %}
      - {{ sock_dir }}
      {% endif %}
    - require:
      - mc_proxy: makina-php-post-inst
    - require_in:
      - mc_proxy: makina-php-pre-restart
{%- endmacro %}

{% macro minimal_index(doc_root, domain='no domain', mode='unkown mode') %}
{{ doc_root }}-minimal-index:
  file.managed:
    - name: {{ doc_root }}/index.php
    - unless: test -e "{{ doc_root }}/index.php"
    - source:
    - contents: '<?php phpinfo(); ?>'
    - makedirs: true
    - user: {{ apacheData.httpd_user }}
    - group: {{ ugs.group }}
    - watch:
      - mc_proxy: postcheckout-project-hook
      - mc_proxy: makina-apache-post-inst
    - watch_in:
      - mc_proxy: makina-apache-pre-conf
      - mc_proxy: makina-php-pre-restart
      - mc_proxy: makina-php-pre-restart
{% endmacro %}
