#
# Install old pythons (ubuntu specific for now)
#
# You can use the grain/pillar following setting to select the  versions:
# makina.localsettings.python_vers: LIST (default: ["2.4", "2.5", "2.6"])
#
# eg:
#
#  salt-call grains.setval makina.localsettings.python_vers '["2.6"]'
#

{% import "makina-states/_macros/localsettings.jinja" as localsettings with context %}

{{ localsettings.register('python') }}
{% set locs = localsettings.locations %}

{% set pyvers = salt['mc_utils.get'](
   'makina.localsettings.python_vers',
   ['2.4', '2.5', '2.6']) %}

{% if grains['os'] in ['Ubuntu'] %}
{% set udist = localsettings.udist %}
deadsnakes:
  pkgrepo.managed:
    - humanname: DeadSnakes PPA
    - name: deb http://ppa.launchpad.net/fkrull/deadsnakes/ubuntu {{udist}} main
    - dist: {{udist}}
    - file: {{locs.conf_dir}}/apt/sources.list.d/deadsnakes.list
    - keyid: DB82666C
    - keyserver: keyserver.ubuntu.com
  {% if pyvers %}
  pkg.installed:
    - require:
      - pkgrepo: deadsnakes
    - pkgs:
      {% for pyver in pyvers %}
      - python{{pyver}}-dev
      - python{{pyver}}
      {% endfor %}
    {% endif %}
{% endif %}
# vim:set nofoldenable:
