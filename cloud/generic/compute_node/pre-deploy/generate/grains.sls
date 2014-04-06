include:
  - makina-states.cloud.generic.hooks.generate
{% set localsettings = salt['mc_localsettings.settings']() %}
{% set cloudSettings = salt['mc_cloud.settings']() %}
{% set compute_node_settings = salt['mc_cloud_compute_node.settings']() %}
{% for target, data in compute_node_settings['targets'].items() %}
{% set cptslsname = '{1}/{0}/compute_node_grains'.format(target.replace('.', ''),
                                                   cloudSettings.compute_node_sls_dir) %}
{% set cptsls = '{1}/{0}.sls'.format(cptslsname, cloudSettings.root) %}
{% set rcptslsname = '{1}/{0}/run-compute_node_grains'.format(target.replace('.', ''),
                                                   cloudSettings.compute_node_sls_dir) %}
{% set rcptsls = '{1}/{0}.sls'.format(rcptslsname, cloudSettings.root) %}
{{target}}-gen-grains-installation:
  file.managed:
    - name: {{cptsls}}
    - makedirs: true
    - mode: 750
    - user: root
    - group: {{localsettings.group}}
    - contents: |
                {%raw%}{# WARNING THIS STATE FILE IS GENERATED #}{%endraw%}
                {{target}}-run-grains:
                  grains.present:
                    - names:
                      - makina-states.services.proxy.haproxy
                      - makina-states.services.firewall.shorewall
                      - makina-states.cloud.compute_node.has.firewall
                      - makina-states.cloud.is.compute_node
                    - value: true
                {{ target }}-reload-grains:
                  cmd.script:
                    - source: salt://makina-states/_scripts/reload_grains.sh
                    - template: jinja
                    - watch:
                      - grains: {{target}}-run-grains
    - watch:
      - mc_proxy: cloud-generic-generate
    - watch_in:
      - mc_proxy: cloud-generic-generate-end
{{target}}-gen-grains-installation-run:
  file.managed:
    - name: {{rcptsls}}
    - makedirs: true
    - mode: 750
    - user: root
    - group: {{localsettings.group}}
    - watch:
      - mc_proxy: cloud-generic-generate
    - watch_in:
      - mc_proxy: cloud-generic-generate-end
    - contents: |
                {%raw%}{# WARNING THIS STATE FILE IS GENERATED #}{%endraw%}
                include:
                  - makina-states.cloud.generic.hooks.compute_node
                {{target}}-run-grains-installation:
                  salt.state:
                    - tgt: [{{target}}]
                    - expr_form: list
                    - sls: {{cptslsname.replace('/', '.')}}
                    - concurrent: True
                    - watch:
                      - mc_proxy: cloud-generic-compute_node-pre-grains-deploy
                    - watch_in:
                      - mc_proxy: cloud-generic-compute_node-post-grains-deploy
{% endfor %}
