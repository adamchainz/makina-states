include:
  - makina-states.nodetypes.vm
  - makina-states.localsettings.pkgs.hooks
  - makina-states.nodetypes.container-hooks

lxc-container-pkgs:
  pkg.{{salt['mc_pkgs.settings']()['installmode']}}:
    - pkgs:
      - apt-utils
      - libfuse2
    - watch:
      - mc_proxy: makina-lxc-proxy-pkgs-pre
    - watch_in:
      - mc_proxy: makina-lxc-proxy-pkgs

etc-init-lxc-setup:
  file.managed:
    - name: /etc/init/lxc-setup.conf
    - source: salt://makina-states/files/etc/init/lxc-setup.conf
    - user: root
    - group: root
    - mode: 0755
    - watch:
      - mc_proxy: makina-lxc-proxy-pkgs
    - watch_in:
      - mc_proxy: makina-lxc-proxy-cfg

lxc-cleanup:
  file.managed:
    - name: /sbin/lxc-cleanup.sh
    - source: salt://makina-states/files/sbin/lxc-cleanup.sh
    - user: root
    - group: root
    - mode: 0755
    - watch:
      - mc_proxy: makina-lxc-proxy-pkgs
    - watch_in:
      - mc_proxy: makina-lxc-proxy-cfg

etc-init-lxc-stop:
  file.managed:
    - name: /etc/init/lxc-stop.conf
    - source: salt://makina-states/files/etc/init/lxc-stop.conf
    - user: root
    - group: root
    - mode: 0755
    - watch:
      - mc_proxy: makina-lxc-proxy-pkgs
    - watch_in:
      - mc_proxy: makina-lxc-proxy-cfg

lxc-install-non-harmful-packages:
  file.managed:
    - source: salt://makina-states/_scripts/build_lxccorepackages.sh
    - name: /sbin/build_lxccorepackages.sh
    - user: root
    - group: root
    - mode: 750
    - watch:
      - mc_proxy: makina-lxc-proxy-pkgs
    - watch_in:
      - mc_proxy: makina-lxc-proxy-cfg
  cmd.run:
    - name: /sbin/build_lxccorepackages.sh
    - watch:
      - mc_proxy: makina-lxc-proxy-build
    - watch_in:
      - mc_proxy: makina-lxc-proxy-mark

do-lxc-cleanup:
  cmd.run:
    - name: /sbin/lxc-cleanup.sh
    - watch:
      - mc_proxy: makina-lxc-proxy-cleanup
    - watch_in:
      - mc_proxy: makina-lxc-proxy-end
