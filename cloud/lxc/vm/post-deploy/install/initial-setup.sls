{% set cloudSettings= salt['mc_cloud.settings']() %}
{% set compute_node_settings = salt['mc_cloud_compute_node.settings']() %}
{% set lxcSettings= salt['mc_cloud_lxc.settings']() %}
include:
  - makina-states.cloud.generic.hooks.vm

{% for target, vms in lxcSettings.vms.items() %}
{%  for vmname, data in vms.items() -%}
{%    set sname = '{0}-{1}'.format(target, vmname) %}
{% if compute_node_settings.targets[target].virt_types.lxc %}
{% set cptslsname = '{1}/{0}/lxc/{2}/run-initial-setup'.format(
        target.replace('.', ''),
        cloudSettings.compute_node_sls_dir,
        vmname.replace('.', '')) %}
{% set cptsls = '{1}/{0}.sls'.format(cptslsname, cloudSettings.root) %}
  - {{cptslsname.replace('/', '.')}}
{%   endif %}
{%   endfor %}
{% endfor %}
