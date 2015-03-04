# -*- coding: utf-8 -*-
'''
.. _module_mc_nscd.py:

mc_nscd.py / ulogd functions
==================================
'''

__docformat__ = 'restructuredtext en'
# Import python libs
import logging
import os
import mc_states.utils

__name = 'nscd'

log = logging.getLogger(__name__)


def settings():
    '''
    nscd settings


    '''
    @mc_states.utils.lazy_subregistry_get(__salt__, __name)
    def _settings():
        grains = __grains__
        pillar = __pillar__
        data = __salt__['mc_utils.defaults'](
            'makina-states.localsettings.nscd', {
                'service_enabled': True,
                'service_name': 'nscd',
            }
        )
        return data
    return _settings()



#
