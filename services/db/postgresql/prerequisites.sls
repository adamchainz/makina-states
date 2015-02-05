{%- import "makina-states/services/db/postgresql/hooks.sls" as hooks with context %}

include:
  - makina-states.services.db.postgresql.hooks
  - makina-states.services.db.postgresql.client

{%- set orchestrate = hooks.orchestrate %}
{%- set locs = salt['mc_locations.settings']() %}
{% set pkgs = salt['mc_pkgs.settings']() %}
{% set settings = salt['mc_pgsql.settings']() %}

postgresql-pkgs:
  pkg.{{salt['mc_pkgs.settings']()['installmode']}}:
    - pkgs:
      - python-virtualenv {# noop #}
      {% if grains['os_family'] in ['Debian'] %}
      {% for pgver in settings.versions %}
      - postgresql-{{pgver}}
      - postgresql-server-dev-{{pgver}}
      - postgresql-{{pgver}}-pgextwlist
      {% endfor %}
      - libpq-dev
      - pgtune
      - postgresql-contrib
      {% endif %}
    {% if grains['os_family'] in ['Debian'] %}
    - require:
      - pkgrepo: pgsql-repo
      - pkg: postgresql-pkgs-client
      - mc_proxy: {{orchestrate['base']['prepkg']}}
    - require_in:
      - mc_proxy: {{orchestrate['base']['postpkg']}}
    {% endif %}
