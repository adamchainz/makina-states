{%- set vmdata = salt['mc_cloud_vm.settings']() %}
{%- set data = vmdata.vts.lxc %}
{% set extra_confs = {} %}
include:
  - makina-states.services.virt.lxc.hooks
  - makina-states.services.virt.lxc.services

{% if salt['mc_controllers.mastersalt_mode']() %}
{% if grains['os'] in ['Ubuntu'] -%}
{% set extra_confs = {'/etc/init/lxc-net-makina.conf': {}} %}

{% elif grains['os'] in ['Debian'] -%}
{% set extra_confs = {'/etc/init.d/lxc-net-makina': {}} %}

# assume systemd
{% else %}
{% set extra_confs = {'/etc/systemd/system/lxc-net-makina': {}} %}
{% endif%}

{% set extra_confs = salt['mc_utils.copy_dictupdate'](
  data['host_confs'], extra_confs) %}

{% for f, fdata in extra_confs.items() %}
{% set template = fdata.get('template', 'jinja') %}
lxc-conf-{{f}}:
  file.managed:
    - name: "{{fdata.get('target', f)}}"
    - source: "{{fdata.get('source', 'salt://makina-states/files'+f)}}"
    - mode: "{{fdata.get('mode', 750)}}"
    - user: "{{fdata.get('user', 'root')}}"
    - group:  "{{fdata.get('group', 'root')}}"
    {% if data.get('makedirs', True) %}
    - makedirs: true
    {% endif %}
    {% if template %}
    - template: "{{template}}"
    {%endif%}
    - watch:
      - mc_proxy: lxc-pre-conf
    - watch_in:
      - mc_proxy: lxc-post-conf
{% endfor %}
{% endif %}
