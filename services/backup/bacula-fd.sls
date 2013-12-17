{% import "makina-states/_macros/services.jinja" as services with context %}
{% set localsettings = services.localsettings %}
{% set locs = localsettings.locations %}
{{ services.register('backup.bacula-fd') }}

bacula-fd-pkg:
  pkg.installed:
    - pkgs:
      - bacula-fd

bacula-fd-svc:
  service.nablede:
    - name:  bacula-fd
    - require:
      - file: etc-bacula-bacula-fd.conf

etc-bacula-bacula-fd.conf:
  bacula.fdconfig:
    - name: {{ locs.conf_dir }}/bacula/bacula-fd.conf
    - require:
      - pkg: bacula-fd-pkgs
    - dirname: makina-dir
    - dirpasswd: {{ pillar.get('bacula-dir-pw', 'baculapw') }}
    - fdname: {{ grains['id'] }}
    - fdport: 9102
    - messages: bacula-dir = all, !skipped, !restored
