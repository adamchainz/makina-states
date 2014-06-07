{% import "makina-states/services/php/macros.sls" as php with context %}
{% set phpSettings = salt['mc_php.settings']() %}
include:
  - makina-states.services.php.hooks
  - makina-states.services.php.phpfpm.services

# remove default pool
makina-phpfpm-remove-default-pool:
  file.absent:
    - name : {{ phpSettings.etcdir }}/fpm/pool.d/www.conf

# --------- Pillar based php-fpm pools
{% if 'register-pools' in phpSettings %}
{%   for site,siteDef in phpSettings['register-pools'].items() %}
{%     do siteDef.update({'site': site}) %}
{%     do siteDef.update({'phpSettings': phpSettings}) %}
{{     php.fpm_pool(**siteDef) }}
{%   endfor %}
{% endif %}

