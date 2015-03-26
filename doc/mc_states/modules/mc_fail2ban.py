# -*- coding: utf-8 -*-
'''
.. _module_mc_fail2ban:

mc_fail2ban / fail2ban functions
==================================



'''

__docformat__ = 'restructuredtext en'
# Import python libs
import logging
import os
import mc_states.api

__name = 'fail2ban'

log = logging.getLogger(__name__)


def settings():
    '''
    fail2ban settings

    location
        conf dir
    destemail:
        destination mail for alerts(root@fqdn})
    loglevel
        (3)
    logtarget
        (/var/log/fail2ban.log)
    mail_from
        (fail2ban@makina-corpus.com)
    mail_to
        (root)
    mail_enabled
        (false)
    mail_host
        (localhost)
    mail_port
        (25)
    mail_user
        (foo)
    mail_password
        (bar)
    mail_localtime
        (true)
    mail_subject
        ([Fail2Ban] <section>: Banned <ip>)
    mail_message
       (Hi,<br> The IP <ip> has just been banned by Fail2Ban'
        after <failures> attempts against <section>.<br>'
        Regards,<br> Fail2Ban)
    socket
        (/var/run/fail2ban/fail2ban.sock)
    backend
        (polling)
    bantime
       (86400)
    maxretry
       (10)
    ssh_maxretry
       ({maxretry})
    protocol
       (tcp)
    mta
       (sendmail)
    banaction
        (iptables or shorewall if activated)
    ignoreip
        ([127.0.0.1])
    postfix_enabled
       (false)
    wuftpd_enabled
       (false)
    vsftpd_enabled
       (false)
    proftpd_enabled
       (false)
    pureftpd_enabled
       (false)
    ssh_enabled
       (true)
    recidive_enabled
       (false)
    asterisk_tcp_enabled
       (false)
    asterisk_udp_enabled
       (false)
    named_refused_tcp_enabled
       (false)
    '''
    @mc_states.api.lazy_subregistry_get(__salt__, __name)
    def _settings():
        grains = __grains__
        pillar = __pillar__
        shorewall = __salt__['mc_shorewall.settings']()
        services_registry = __salt__['mc_services.registry']()
        banaction = 'iptables'
        if (
            (
                services_registry['has']['firewall.shorewall']
                and shorewall['shw_enabled']
            ) and (
                os.path.exists('/usr/bin/shorewall')
                or os.path.exists('/sbin/shorewall')
                or os.path.exists('/usr/sbin/shorewall')
                or os.path.exists('/usr/bin/shorewall')
                or os.path.exists('/usr/local/sbin/shorewall')
                or os.path.exists('/usr/local/bin/shorewall')
            )
        ):
            banaction = 'shorewall'
        locs = __salt__['mc_locations.settings']()
        data = __salt__['mc_utils.defaults'](
            'makina-states.services.firewall.fail2ban', {
                'location': locs['conf_dir'] + '/fail2ban',
                'destemail': 'root@{fqdn}'.format(**grains),
                'loglevel': '3',
                'logtarget': '/var/log/fail2ban.log',
                'mail_from': 'fail2ban@makina-corpus.com',
                'mail_to': 'root',
                'mail_enabled': 'false',
                'mail_host': 'localhost',
                'mail_port': '25',
                'mail_user': 'foo',
                'mail_password': 'bar',
                'mail_localtime': 'true',
                'filters': {
                    'wordpress': {
                        'failregex': (
                            '^%(__prefix_line)sWordpress'
                            ' authentication failure for'
                            ' .* from <HOST>$')
                    }

                },
                'jails': {
                    'wordpress': {
                        'filter': 'wordpress',
                        'port': 'http,https',
                    }
                },
                'default_filters_opts': {
                    'ignoreregex': ''
                },
                'default_jail_opts': {
                    'port': 'ssh',
                    'logpath': '/var/log/syslog',
                    'banaction': 'shorewall',
                    'maxretry': 5,
                    'findtime': 600,
                    'bantime': 600,
                    'enabled': False,
                    'filter': 'sshd',
                },
                'mail_subject': (
                    '[Fail2Ban {0}] <section>: Banned <ip>'
                ).format(grains['id']),
                'mail_message': (
                    'Hi,<br> The IP <ip> has just been banned by Fail2Ban'
                    ' after <failures> attempts against <section>.<br>'
                    ' Regards,<br> Fail2Ban'),
                'socket': '/var/run/fail2ban/fail2ban.sock',
                'backend': 'polling',
                'bantime': '86400',
                'maxretry': '10',
                'ssh_maxretry': '{maxretry}',
                'protocol': 'tcp',
                'mta': 'sendmail',
                'banaction': banaction,
                'ignoreip': ['127.0.0.1'],
                'postfix_enabled': 'false',
                'wuftpd_enabled': 'false',
                'vsftpd_enabled': 'false',
                'proftpd_enabled': 'false',
                'pureftpd_enabled': 'false',
                'ssh_enabled': 'true',
                'recidive_enabled': 'false',
                'asterisk_tcp_enabled': 'false',
                'asterisk_udp_enabled': 'false',
                'named_refused_tcp_enabled': 'false',
            }
        )
        # if a filter is defined with the same name of a jail
        # and no filter is defined for this jail
        # make this filter as the jailname
        for item in [a for a in data['jails']]:
            ddata = data['jails'][item]
            if (
                'filter' not in ddata
                and (item in data['filters'])
            ):
                ddata['filter'] = item
        return data
    return _settings()



#
