{% import "makina-states/services/php/macros.sls" as macros with context %}
{% set minimal_index = macros.minimal_index %}
{% set fpm_pool = macros.fpm_pool %}
{% set includes = macros.includes %}
{% set ugs = macros.ugs%}
{% set apacheData = macros.apacheData %}
{% set nodetypes = macros.nodetypes%}
{% set phpData = macros.phpData %}
{% set locs = macros.locs %}
{% set default_pool_template_source = macros.default_pool_template_source %}
