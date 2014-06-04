# -*- coding: utf-8 -*-
'''
.. _module_mc_project_2:

mc_project_2 / project settings regitry APIV2
================================================

'''

import yaml.error
import datetime
import os
import logging
import socket
from pprint import pformat
import shutil
import sys
import traceback
import uuid
import yaml

import copy
from salt.utils.odict import OrderedDict
from salt.states import group as sgroup
from salt.states import user as suser
from salt.states import file as sfile
from salt.states import git as sgit
#from mc_states.states import mc_git as sgit
from salt.states import cmd as scmd
import salt.output
import salt.loader
import salt.utils

from mc_states.utils import is_valid_ip
from mc_states.api import (
    splitstrip,
    msplitstrip,
    indent,
    uniquify,
)

import mc_states.project
from mc_states.project import (
    ENVS,
    KEEP_ARCHIVES,
    ProjectInitException,
    ProjectProcedureException,
)


log = logger = logging.getLogger(__name__)


API_VERSION = '2'
PROJECT_INJECTED_CONFIG_VAR = 'cfg'

DEFAULT_CONFIGURATION = {
    'name': None,
    'default_env': None,
    'installer': 'generic',
    'keep_archives': KEEP_ARCHIVES,
    #
    'user': None,
    'groups': [],
    #
    'raw_console_return': False,
    #
    'only': None,
    'force_reload': False,
    #
    'api_version': API_VERSION,
    #
    'defaults': {},
    'env_defaults': {},
    'os_defaults': {},
    #
    'no_user': False,
    'no_default_includes': False,
    # INTERNAL
    'data': {},
    'deploy_summary': None,
    'deploy_ret': {},
    'push_pillar_url': 'ssh://root@{this_host}:{this_port}{pillar_git_root}',
    'push_salt_url': 'ssh://root@{this_host}:{this_port}{project_git_root}',
    'project_dir': '{projects_dir}/{name}',
    'project_root': '{project_dir}/project',
    'deploy_marker': '{project_root}/.tmp_deploy',
    'salt_root': '{project_root}/.salt',
    'pillar_root': '{project_dir}/pillar',
    'data_root': '{project_dir}/data',
    'archives_root': '{project_dir}/archives',
    'git_root': '{project_dir}/git',
    'project_git_root': '{git_root}/project.git',
    'pillar_git_root': '{git_root}/pillar.git',
    'current_archive_dir': None,
    'rollback': False,
    'this_host': 'localhost',
    'this_port': '22',
    #
}
STEPS = ['deploy',
         'archive',
         'release_sync',
         'install',
         'rotate_archives',
         'rollback',
         'fixperms',
         'notify']
SPECIAL_SLSES = ["{0}.sls".format(a)
                 for a in STEPS
                 if a not in ['deploy',
                              'release_sync',
                              'rotate_archives',
                              'install']]


for step in STEPS:
    DEFAULT_CONFIGURATION['skip_{0}'.format(step)] = None


def _state_exec(*a, **kw):
    return __salt__['mc_state.sexec'](*a, **kw)


def _stop_proc(message, step, ret):
    ret['raw_comment'] = message
    ret['result'] = False
    raise ProjectProcedureException(ret['raw_comment'],
                                    salt_step=step,
                                    salt_ret=ret)


def _check_proc(message, step, ret):
    if not ret['result']:
        _stop_proc(message, step, ret)


def _filter_ret(ret, raw=False):
    if not raw and 'raw_comment' in ret:
        del ret['raw_comment']
    return ret


def _outputters(outputter=None):
    outputters = salt.loader.outputters(__opts__)
    if outputter:
        return outputters[outputter]
    return outputters


def _hs(mapping, raw=False):
    color = __opts__.get('color', None)
    __opts__['color'] = not raw
    ret = _outputters('highstate')({'local': mapping})
    __opts__['color'] = color
    return ret


def _raw_hs(mapping):
    return _hs(mapping, raw=True)


def _force_cli_retcode(ret):
     # cli codeerr = 3 in case of failure
     if not ret['result']:
         __context__['retcode'] = 3
     else:
         __context__['retcode'] = 0


def remove_path(path):
    """Remove a path."""
    if os.path.exists(path):
        if os.path.islink(path):
            os.unlink(path)
        elif os.path.isfile(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    else:
        print
        print "'%s' was asked to be deleted but does not exists." % path
        print

def _sls_exec(name, cfg, sls):
    # be sure of the current project beeing loaded in the context
    set_project(cfg)
    cfg = get_project(name)
    ret = _get_ret(name)
    ret.update({'return': None, 'sls': sls, 'name': name})
    old_retcode = __context__.get('retcode', 0)
    cret = __salt__['state.sls'](sls.format(**cfg))
    ret['return'] = cret
    comment = ''
    __context__.setdefault('retcode', 0)
    if isinstance(cret, dict):
        if not cret:
            ret['result'] = True
            __context__['retcode'] = 0
            _append_comment(ret,
                            'Warning sls:\'{1}\' for project:\'{0}\' '
                            'did not execute any state!'.format(name, sls))

        for lowid, state in cret.items():
            failed = False
            if not isinstance(state, dict):
                # invalid data structure
                failed = True
            else:
                if not state.get('result', False):
                    failed = True
            if failed:
                __context__['retcode'] = 3
                ret['result'] = False
    if __context__['retcode'] > 0:
        ret['result'] = False
        body = ''
        if isinstance(cret, list):
            body += indent(cret)
        _append_comment(ret,
                        'Running {1} for {0} failed'.format(name, sls),
                        body=body)
    if cret and isinstance(cret, dict):
        _append_comment('SLS execution result of {0} for {1}:'.format(sls,
                                                                      name))
        ret['raw_comment'] += indent(_raw_hs(copy.deepcopy(cret)))
        ret['comment'] += indent(_hs(copy.deepcopy(cret)))
    msplitstrip(ret)
    return ret


def _get_ret(name, *args, **kwargs):
    ret = kwargs.get('ret', None)
    if ret is None:
        ret = {'comment': '',
               'raw_comment': '',
               'result': True,
               'changes': {},
               'name': name}
    return ret


def _colors(color=None):
    colors = salt.utils.get_colors(__opts__.get('color'))
    if color:
        return colors[color]
    return colors


def _append_comment(ret,
                    summary=None,
                    body=None,
                    color='YELLOW'):
    if body:
        colon = ':'
    else:
        colon = ''
    if summary:
        if 'raw_comment' in ret:
            ret['raw_comment'] += '\n{0}\n'.format(summary)
        if 'comment' in ret:
            ret['comment'] += '\n{0}{2}{3}{1}\n'.format(
                _colors(color), _colors('ENDC'), summary, colon)
    if body:
        rbody = '\n{0}\n'.format(body)
        ret['comment'] += rbody
        if 'raw_comment' in ret:
            ret['raw_comment'] += rbody

    return ret


def _append_separator(ret, separator='--', separator_color='LIGHT_CYAN'):
    if not 'raw_comment' in ret:
        ret['raw_comment'] = ''
    if separator:
        ret['raw_comment'] += '\n{0}'.format(separator)
        ret['comment'] += '\n{0}{2}{1}\n'.format(
            _colors(separator_color), _colors('ENDC'), separator)


def _step_exec(cfg, step, failhard=True):
    # be sure of the current project beeing loaded in the context
    name = cfg['name']
    sls = 'makina-projects.{0}.{1}'.format(name, step)
    skip_flag = 'skip_{0}'.format(step)
    skipped = cfg.get(skip_flag, False)
    # XXX: REMOVE ME after tests !!! (False)
    # skipped = False
    if skipped:
        cret = _get_ret(name)
        cret.update({'result': True,
                     'comment': (
                         'Warning: Step {0} for project '
                         '{1} was skipped').format(step, name),
                     'return': None,
                     'name': name})
    else:
        cret = _sls_exec(name, cfg, sls)
    _force_cli_retcode(cret)
    if failhard:
        _check_proc(
            'Deploy step "{0}" for project "{1}" failed, '
            'we can not continued'.format(step, name), step, cret)
    return _filter_ret(cret, cfg['raw_console_return'])


def get_default_configuration():
    conf = copy.deepcopy(DEFAULT_CONFIGURATION)
    this_host, this_port = 'localhost', '22'
    if os.path.exists('/this_port'):
        this_port = open('/this_port').read()
    if os.path.exists('/this_host'):
        this_host = open('/this_host').read()
    conf['this_host'] = this_host
    conf['this_port'] = this_port
    return conf


def _defaultsConfiguration(
    cfg,
    default_env,
    defaultsConfiguration=None,
    env_defaults=None,
    os_defaults=None
):
    salt = __salt__
    # load sample if present
    sample = os.path.join(cfg['wired_salt_root'],
                          'PILLAR.sample')
    if defaultsConfiguration is None:
        defaultsConfiguration = {}
    if os.path.exists(sample):
        try:
            sample_data = OrderedDict()
            with open(sample) as fic:
                sample_data_l = __salt__['mc_utils.cyaml_load'](fic.read())
                if not isinstance(sample_data_l, dict):
                    sample_data_l = OrderedDict()
                for k, val in sample_data_l.items():
                    if isinstance(val, dict):
                        for k2, val2 in val.items():
                            if isinstance(val2, dict):
                                sample_data.update(val2)
                            else:
                                sample_data[k2] = val2
                    else:
                        sample_data[k] = val
        except yaml.error.YAMLError:
            trace = traceback.format_exc()
            error = (
                '{0}\n{1} is not a valid YAML File for {2}'.format(
                    trace, sample, cfg['name']))
            log.error(error)
            raise ValueError(error)
        except Exception, exc:
            trace = traceback.format_exc()
            log.error(trace)
            sample_data = OrderedDict()
            cfg['force_reload'] = True
        defaultsConfiguration.update(sample_data)
    _dict_update = salt['mc_utils.dictupdate']
    _defaults = salt['mc_utils.defaults']
    if os_defaults is None:
        os_defaults = OrderedDict()
    if env_defaults is None:
        env_defaults = OrderedDict()
    if not env_defaults:
        env_defaults = _dict_update(
            env_defaults,
            salt['mc_utils.get'](
                'makina-projects.{name}.env_defaults'.format(**cfg),
                {}))
        env_defaults = _dict_update(
            env_defaults,
            salt['mc_utils.get'](
                'makina-projects.{name}'.format(**cfg),
                OrderedDict()
            ).get('env_defaults', OrderedDict()))
    if not os_defaults:
        os_defaults = _dict_update(
            os_defaults,
            salt['mc_utils.get'](
                'makina-projects.{name}.os_defaults'.format(**cfg),
                {}))
        os_defaults = _dict_update(
            os_defaults,
            salt['mc_utils.get'](
                'makina-projects.{name}'.format(**cfg),
                OrderedDict()
            ).get('os_defaults', OrderedDict()))
    pillar_data = {}
    pillar_data = _dict_update(
         pillar_data,
         salt['mc_utils.get'](
             'makina-projects.{name}.data'.format(**cfg),
             OrderedDict()))

    memd_data = salt['mc_utils.get'](
        'makina-projects.{name}'.format(**cfg),
        OrderedDict()
    ).get('data', OrderedDict())
    if not isinstance(memd_data, dict):
        raise ValueError(
            'data is not a dict for {0}, '
            'review your pillar and yaml files'.format(
                cfg.get('name', 'project')))
    pillar_data = _dict_update(pillar_data, memd_data)
    os_defaults.setdefault(__grains__['os'], OrderedDict())
    os_defaults.setdefault(__grains__['os_family'],
                           OrderedDict())
    env_defaults.setdefault(default_env, OrderedDict())
    for k in ENVS:
        env_defaults.setdefault(k, OrderedDict())
    defaultsConfiguration = salt['mc_utils.dictupdate'](
        defaultsConfiguration, pillar_data)
    defaultsConfiguration = salt['mc_utils.dictupdate'](
        defaultsConfiguration,
        salt['grains.filter_by'](
            env_defaults, grain=default_env, default="dev"))
    defaultsConfiguration = salt['mc_utils.dictupdate'](
        defaultsConfiguration,
        salt['grains.filter_by'](os_defaults, grain='os_family'))
    # retro compat 'foo-default-settings'
    defaultsConfiguration = salt['mc_utils.defaults'](
        '{name}-default-settings'.format(**cfg),
        defaultsConfiguration)
    # new location 'makina-projects.foo.data'
    defaultsConfiguration = salt['mc_utils.defaults'](
        'makina-projects.{name}.data'.format(**cfg),
        defaultsConfiguration)
    return defaultsConfiguration


def _merge_statuses(ret, cret, step=None):
    for d in ret, cret:
        if not 'raw_comment' in d:
            d['raw_comment'] = ''
    _append_separator(ret)
    if cret['result'] is False:
        ret['result'] = False
    if cret.get('changes', {}) and ('changes' in ret):
        ret['changes'].update(cret)
    if step:
        ret['comment'] += '\n{3}Execution step:{2} {1}{0}{2}'.format(
            step, _colors('YELLOW'), _colors('ENDC'), _colors('RED'))
        ret['raw_comment'] += '\nExecution step: {0}'.format(cret)
    for k in ['raw_comment', 'comment']:
        if k in cret:
            ret[k] += '\n{{{0}}}'.format(k).format(**cret)
    if not ret['result']:
        _append_comment(ret,
                        summary='Deployment aborted due to error',
                        color='RED')
    return ret


def _init_context():
    if not 'ms_projects' in __opts__:
        __opts__['ms_projects'] = OrderedDict()
    if not 'ms_project_name' in __opts__:
        __opts__['ms_project_name'] = None
    if not 'ms_project' in __opts__:
        __opts__['ms_project'] = None


def set_project(cfg):
    _init_context()
    __opts__['ms_project_name'] = cfg['name']
    __opts__['ms_project'] = cfg
    __opts__['ms_projects'][cfg['name']] = cfg
    return cfg


def get_project(name):
    '''Alias of get_configuration for convenience'''
    return get_configuration(name)


def _get_contextual_cached_project(name):
    _init_context()
    # throw KeyError if not already loaded
    cfg = __opts__['ms_projects'][__opts__['ms_project_name']]
    __opts__['ms_project'] = cfg
    __opts__['ms_project_name'] = cfg['name']
    return cfg


def get_configuration(name, *args, **kwargs):
    """
    Return a configuration data structure needed data for
    the project API macros and configurations functions
    project API 2

    name
        name of the project
    default_env
        environnemt to run into (may be dev|prod, better
        to set a grain see bellow)
    project_root
        where to install the project,
    git_root
        root dir for git repositories
    user
        system project user
    groups
        system project user groups, first group is main
    defaults
        arbitrary data mapping for this project to use in states.
        It will be accessible throught the get_configuration().data var
    env_defaults
        per environment (eg: prod|dev) specific defaults data to override or
        merge inside the defaults one
    os_defaults
        per os (eg: Ubuntu/Debian) specific defaults data to override or merge
        inside the defaults one

    only_install
        Only run the install step (make the others skipped)
    skip_archive
        Skip the archive step
    skip_release_sync
        Skip the release_sync step
    skip_install
        Skip the install phase
    skip_rollback
        Skip the rollback step if any
    skip_notify
        Skip the notify step if any

    Internal variables reference

        pillar_root
            pillar local dir
        salt_root
            salt local dir
        archives_root
            archives directory
        data_root
            persistent data root
        project_git_root
            project local git dir
        pillar_git_root
            pillar local git dir
        data
            The final mapping where all defaults will be mangled.
            If you want to add extra parameters in the configuration, you d
            better have to add them to defaults.
        force_reload
            if the project configuration is already present in the context,
            reload it anyway
        sls_includes
            includes to add to the project top includes statement
        no_default_includes
            Do not add salt_minon & other bases sls
            like ssh to default includes
        rollback
            FLAG: do we rollback at the end of all processes

    You can override the non read only default variables
    by pillar/grain like::

        salt grain.setval makina-projects.foo.url 'http://goo/goo.git
        salt grain.setval makina-projects.foo.default_env prod

    You can override the non read only default arbitrary attached defaults
    by pillar/grain like::

        /srv/projects/foo/pillar/init.sls:

        makina-projects.foo.data.conf_port = 1234

    """
    try:
        cfg = _get_contextual_cached_project(name)
        if cfg['force_reload'] or kwargs.get('force_reload', False):
            raise KeyError('reload me!')
        return cfg
    except KeyError:
        pass
    cfg = get_default_configuration()
    cfg['name'] = name
    cfg.update(dict([a
                     for a in kwargs.items()
                     if a[0] in cfg]))
    # we must also ignore keys setted on the call to the function
    # which are explictly setting a value
    ignored_keys = ['data', 'rollback']
    for k in kwargs:
        if k in cfg:
            ignored_keys.append(k)
    nodetypes_reg = __salt__['mc_nodetypes.registry']()
    salt_settings = __salt__['mc_salt.settings']()
    salt_root = salt_settings['saltRoot']
    # special symlinks inside salt wiring
    cfg['wired_salt_root'] = os.path.join(
        salt_settings['saltRoot'], 'makina-projects', cfg['name'])
    cfg['wired_pillar_root'] = os.path.join(
        salt_settings['pillarRoot'], 'makina-projects', cfg['name'])
    # check if the specified sls installer files container
    if not cfg['default_env']:
        # one of:
        # - makina-projects.fooproject.default_env
        # - fooproject.default_env
        # - default_env
        cfg['default_env'] = __salt__['mc_utils.get'](
            'makina-projects.{0}.{1}'.format(name, 'default_env'),
            __salt__['mc_utils.get'](
                '{0}.{1}'.format(name, 'default_env'),
                __salt__['mc_utils.get']('default_env', 'dev')))

    # set default skippped steps on a specific environment
    # to let them maybe be overriden in pillar
    skipped = {}
    for step in STEPS:
        ignored_keys.append('skip_{0}'.format(step))
        skipped['skip_{0}'.format(step)] = kwargs.get(
            'skip_{0}'.format(step), False)
    only = kwargs.get('only', cfg.get('only', None))
    if only:
        if isinstance(only, basestring):
            only = only.split(',')
        if not isinstance(only, list):
            raise ValueError('invalid only for {1}: {0}'.format(only, cfg['name']))
    if only:
        forced = ['skip_deploy'] + ['skip_{0}'.format(o) for o in only]
        for s in [a for a in skipped]:
            if not skipped[s] and not s in forced:
                skipped[s] = True
        for s in forced:
            skipped[s] = False
    cfg.update(skipped)
    #
    if not cfg['user']:
        cfg['user'] = '{name}-user'
    if not cfg['groups']:
        cfg['groups'].append(__salt__['mc_usergroup.settings']()['group'])
    cfg['groups'] = uniquify(cfg['groups'])
    # those variables are overridable via pillar/grains
    overridable_variables = ['default_env',
                             'keep_archives',
                             'no_user',
                             'no_default_includes']

    # we can override many of default values via pillar/grains
    for k in overridable_variables:
        if k in ignored_keys:
            continue
        cfg[k] = __salt__['mc_utils.get'](
            'makina-projects.{0}.{1}'.format(name, k), cfg[k])
    try:
        cfg['keep_archives'] = int(cfg['keep_archives'])
    except (TypeError, ValueError, KeyError):
        cfg['keep_archives'] = KEEP_ARCHIVES
    cfg['data'] = _defaultsConfiguration(cfg,
                                         cfg['default_env'],
                                         defaultsConfiguration=cfg['defaults'],
                                         env_defaults=cfg['env_defaults'],
                                         os_defaults=cfg['os_defaults'])
    # some vars need to be setted just a that time
    cfg['group'] = cfg['groups'][0]
    cfg['projects_dir'] = __salt__['mc_locations.settings']()['projects_dir']

    # finally resolve the format-variabilized dict key entries in
    # arbitrary conf mapping
    cfg['data'] = __salt__['mc_utils.format_resolve'](cfg['data'])
    cfg['data'] = __salt__['mc_utils.format_resolve'](cfg['data'], cfg)

    # finally resolve the format-variabilized dict key entries in global conf
    cfg.update(__salt__['mc_utils.format_resolve'](cfg))
    cfg.update(__salt__['mc_utils.format_resolve'](cfg, cfg['data']))

    # we can try override default values via pillar/grains a last time
    # as format_resolve can have setted new entries
    # we do that only on the global data level and on non read only vars
    if 'data' not in ignored_keys:
        ignored_keys.append('data')
    cfg.update(
        __salt__['mc_utils.defaults'](
            'makina-projects.{0}'.format(name),
            cfg, ignored_keys=ignored_keys))
    now = datetime.datetime.now()
    cfg['chrono'] = '{0}_{1}'.format(
        datetime.datetime.strftime(now, '%Y-%m-%d_%H_%M-%S'),
        str(uuid.uuid4()))
    cfg['current_archive_dir'] = os.path.join(
        cfg['archives_root'], cfg['chrono'])

    # exists
    if '/' not in cfg['installer']:
        installer_path = os.path.join(
            salt_root, 'makina-states/projects/{0}/{1}'.format(
                cfg['api_version'], cfg['installer']))
    # check for all sls to be in there
    cfg['installer_path'] = installer_path
    # put the result inside the context
    set_project(cfg)
    return cfg


def _get_filtered_cfg(cfg):
    ignored_keys = ['data',
                    'name',
                    'salt_root',
                    'rollback']
    to_save = {}
    for sk in cfg:
        val = cfg[sk]
        if sk.startswith('skip_'):
            continue
        if sk.startswith('__pub'):
            continue
        if sk in ignored_keys:
            continue
        if isinstance(val, OrderedDict) or isinstance(val, dict):
            continue
        to_save[sk] = val
    return to_save


def set_configuration(name, cfg=None, *args, **kwargs):
    '''set or update a local (grains) project configuration'''
    if not cfg:
        cfg = get_configuration(name, *args, **kwargs)
    __salt__['grains.setval']('makina-projects.{0}'.format(name),
                              _get_filtered_cfg(cfg))
    return get_configuration(name)


def init_user_groups(user, groups=None, ret=None):
    _append_comment(
        ret, summary='Verify user:{0} & groups:{1} for project'.format(
            user, groups))
    _s = __salt__.get
    if not groups:
        groups = []
    if not ret:
        ret = _get_ret(user)
    # create user if any
    for g in groups:
        if not _s('group.info')(g):
            cret = _state_exec(sgroup, 'present', g, system=True)
            if not cret['result']:
                raise ProjectInitException('Can\'t manage {0} group'.format(g))
            else:
                _append_comment(ret, body=indent(cret['comment']))
    if not _s('user.info')(user):
        cret = _state_exec(suser, 'present',
                           user,
                           home='/home/users/{0}'.format(user),
                           shell='/bin/bash',
                           gid_from_name=True,
                           remove_groups=False,
                           optional_groups=groups)
        if not cret['result']:
            raise ProjectInitException(
                'Can\'t manage {0} user'.format(user))
        else:
            _append_comment(ret, body=indent(cret['comment']))
    return ret


def init_project_dirs(cfg, ret=None):
    _s = __salt__.get
    if not ret:
        ret = _get_ret(cfg['name'])
    _append_comment(ret, summary=(
        'Initialize or verify core '
        'project layout for {0}').format(cfg['name']))
    # create various directories
    for dr, mode in [
        (cfg['git_root'], '770'),
        (cfg['archives_root'], '770'),
        (os.path.dirname(cfg['wired_pillar_root']), '770'),
        (os.path.dirname(cfg['wired_salt_root']), '770'),
        (cfg['data_root'], '770'),
    ]:
        cret = _state_exec(sfile,
                           'directory',
                           dr,
                           makedirs=True,
                           user=cfg['user'],
                           group=cfg['group'],
                           mode='750')
        if not cret['result']:
            raise ProjectInitException(
                'Can\'t manage {0} dir'.format(dr))
        #else:
        #    _append_comment(ret, body=indent(cret['comment']))
    for symlink, target in (
        (cfg['wired_salt_root'], cfg['salt_root']),
        (cfg['wired_pillar_root'], cfg['pillar_root']),
    ):
        cret = _state_exec(sfile, 'symlink', symlink, target=target)
        if not cret['result']:
            raise ProjectInitException(
                'Can\'t manage {0} -> {1} symlink\n{2}'.format(
                    symlink, target, cret))
        #else:
        #    _append_comment(ret, body=indent(cret['comment']))
    return ret


def init_ssh_user_keys(user, failhard=False, ret=None):
    '''Copy root keys from root to a user
    to allow user to share the same key than root to clone distant repos.
    This is useful in vms (local PaaS vm)
    '''
    _append_comment(
        ret, summary='SSH keys management for {0}'.format(user))
    cmd = '''
home="$(awk -F: -v v="{user}" '{{if ($1==v && $6!="") print $6}}' /etc/passwd)";
cd /root/.ssh;
chown {user} $home;
if [ ! -e $home/.ssh ];then
  mkdir $home/.ssh;
fi;
for i in config id_*;do
  if [ ! -e $home/.ssh/$i ];then
    cp -fv $i $home/.ssh;
  fi;
done;
chown -Rf {user}:{user} $home/.ssh;
chmod -Rf 700 $home/.ssh/*;
echo;echo "changed=false comment='do no trigger changes'"
'''.format(user=user)
    onlyif = '''res=1;
home="$(awk -F: -v v="{user}" '{{if ($1==v && $6!="") print $6}}' /etc/passwd)";
cd /root/.ssh;
if [ "x$(stat -c %U "$home")" != "x$user" ];then
    res=0
fi
for i in config id_*;do
  if [ ! -e $home/.ssh/$i ];then
    res=0;
  fi;
done;
exit $res;'''.format(user=user)
    if not ret:
        ret = _get_ret(user)
    _s = __salt__.get
    cret = _state_exec(scmd, 'run', cmd, onlyif=onlyif, stateful=True)
    if failhard and not cret['result']:
        raise ProjectInitException('SSH keys improperly configured\n'
                                   '{0}'.format(cret))
    #else:
    #    _append_comment(ret, body=indent('SSH keys in place if any'))
    return ret


def sync_hooks(name, git, user, group, deploy_hooks=False,
               ret=None, bare=True, api_version=API_VERSION):
    _s = __salt__.get
    if not ret:
        ret = _get_ret(user)
    lgit = git
    if not bare:
        lgit = os.path.join(lgit, '.git')
    cret = _state_exec(sfile, 'managed',
                       name=os.path.join(lgit, 'hooks/pre-receive'),
                       source=(
                           'salt://makina-states/files/projects/2/'
                           'hooks/pre-receive'),
                       defaults={'api_version': api_version, 'name': name},
                       user=user, group=group, mode='750', template='jinja')
    cret = _state_exec(sfile, 'managed',
                       name=os.path.join(lgit, 'hooks/post-receive'),
                       source=(
                           'salt://makina-states/files/projects/2/'
                           'hooks/post-receive'),
                       defaults={'api_version': api_version, 'name': name},
                       user=user, group=group, mode='750', template='jinja')
    cret = _state_exec(sfile, 'managed',
                       name=os.path.join(lgit, 'hooks/deploy_hook.py'),
                       source=(
                           'salt://makina-states/files/projects/2/'
                           'hooks/deploy_hook.py'),
                       defaults={'api_version': api_version, 'name': name},
                       user=user, group=group, mode='750')
    if not cret['result']:
        raise ProjectInitException(
            'Can\'t set git hooks for {0}\n{1}'.format(git, cret['comment']))
    else:
        _append_comment(
            ret, summary='Git Hooks for {0}'.format(git))
        #_append_comment(ret, body=indent(cret['comment']))


def init_repo(cfg, git, user, group, deploy_hooks=False,
                   ret=None, bare=True, init_salt=False,
                   init_pillar=False, api_version=API_VERSION):
    _s = __salt__.get
    if not ret:
        ret = _get_ret(user)
    pref = 'Bare r'
    if not bare:
        pref = 'R'
    _append_comment(
        ret, summary='{1}epository managment in {0}'.format(git, pref))
    lgit = git
    if not bare:
        lgit = os.path.join(lgit, '.git')
    if os.path.exists(lgit):
        cmd = 'chown -Rf {0} "{2}"'.format(user, group, git)
        cret = _s('cmd.run_all')(cmd)
        if cret['retcode']:
            raise ProjectInitException(
                'Can\'t set perms for {0}'.format(git))
    parent = os.path.dirname(git)
    cret = _state_exec(sfile, 'directory',
                       parent,
                       makedirs=True,
                       user=user,
                       group=group,
                       mode='770')
    if not cret['result']:
        raise ProjectInitException(
            'Can\'t manage {0} dir'.format(git))
    #else:
    #    _append_comment(ret, body=indent(cret['comment']))
    # initialize an empty git
    cret = _state_exec(sgit,
                       'present',
                       git,
                       user=user,
                       bare=bare,
                       force=True)
    if not cret['result']:
        raise ProjectInitException(
            'Can\'t manage {0} dir'.format(git))
    #else:
    #    _append_comment(ret, body=indent(cret['comment']))
    if len(os.listdir(lgit + '/refs/heads')) < 1:
        igit = lgit
        if bare:
            igit += '.tmp'
        cret = _s('cmd.run_all')(
            ('mkdir -p "{0}" &&'
             ' cd "{0}" &&'
             ' git init &&'
             ' touch .empty &&'
             ' git config user.email "makinastates@paas.tld" &&'
             ' git config user.name "makinastates" &&'
             ' git add .empty &&'
             ' git commit -am "initial" &&'
             ' git remote add origin {1} &&'
             ' git push -u origin master'
            ).format(igit, lgit),
            runas=user
        )
        if cret['retcode']:
            raise ProjectInitException(
                'Can\'t add first commit in {0}'.format(git))
        if bare and (init_salt or init_pillar):
            if init_salt:
                init_salt_dir(cfg, lgit+".tmp", ret=ret)
            if init_pillar:
                init_pillar_dir(cfg, lgit+".tmp", ret=ret)
            cret = _s('cmd.run_all')(
                ('cd "{0}.tmp" &&'
                 ' git add . &&'
                 ' git commit -m "salt init"').format(lgit),
                runas=user
            )
            if cret['retcode']:
                raise ProjectInitException(
                    'Can\'t commit salt commit in {0}'.format(git))
            cret = _s('cmd.run_all')(
                ('cd "{0}.tmp" &&'
                 ' git push origin -u master').format(lgit),
                runas=user
            )
            if cret['retcode']:
                raise ProjectInitException(
                    'Can\'t push first salt commit in {0}'.format(git))
        if bare:
            cret = _s('cmd.run_all')(
                ('rm -rf "{0}.tmp"').format(lgit), runas=user)
    #else:
    #    _append_comment(
    #        ret, body=indent('Commited first commit in {0}'.format(git)))
    return ret


def init_local_repository(wc, url, user, group, ret=None):
    _s = __salt__.get
    _append_comment(
        ret, summary='Local git repository initialization in {0}'.format(wc))
    if not ret:
        ret = _get_ret(user)
    parent = os.path.dirname(wc)
    cret = _state_exec(sfile, 'directory',
                       parent,
                       makedirs=True,
                       user=user,
                       group=group,
                       mode='770')
    if not cret['result']:
        raise ProjectInitException(
            'Can\'t manage {0} dir'.format(wc))
    else:
        _append_comment(ret, body=indent(cret['comment']))
    # initialize an empty git for pillar & project
    cret = _state_exec(sgit, 'present',
                       wc,
                       bare=False,
                       user=user,
                       force=True)
    if not cret['result']:
        raise ProjectInitException(
            'Can\'t initialize git dir  {0} dir'.format(wc))
    #else:
    #    _append_comment(ret, body=indent(cret['comment']))


def set_git_remote(wc, user, localgit, remote='origin', ret=None):
    _s = __salt__.get
    _append_comment(
        ret, summary=('Set remotes in local copy {0} -> {1}'.format(
            localgit, wc)))
    if not ret:
        ret = _get_ret(user)
    # add the local and distant remotes
    cret = _s('git.remote_set')(localgit, remote, wc , user=user)
    if not cret:
        raise ProjectInitException(
            'Can\'t initialize git local remote '
            '{0} from {1} in {2}'.format(
                remote, lurl, wc))
        #else:
        #    _append_comment(ret,
        #                    body=indent('LocalRemote {0} -> {1} set'.format(
        #                        remote, lurl)))
    return ret


def fetch_last_commits(wc, user, origin='origin', ret=None):
    _s = __salt__.get
    if not ret:
        ret = _get_ret(user)
    _append_comment(
        ret, summary=('Fetch last commits from {1} '
                      'in working copy: {0}'.format(
                          wc, origin)))
    cret = _s('cmd.run_all')(
        'git fetch {0}'.format(origin), cwd=wc, runas=user)
    if cret['retcode']:
        raise ProjectInitException('Can\'t fetch git in {0}'.format(wc))
    cret = _s('cmd.run_all')(
        'git fetch {0} --tags'.format(origin), cwd=wc, runas=user)
    if cret['retcode']:
        raise ProjectInitException('Can\'t fetch git tags in {0}'.format(wc))
    #else:
    #    out = splitstrip('{stdout}\n{stderr}'.format(**cret))
    #    _append_comment(ret, body=indent(out))
    return ret


def has_no_commits(wc, user='root'):
    _s = __salt__.get
    nocommits = "fatal: bad default revision 'HEAD'" in _s('cmd.run')(
        'git log', env={'LANG': 'C', 'LC_ALL': 'C'},
        cwd=wc, user=user)
    return nocommits


def set_upstream(wc, rev, user, origin='origin', ret=None):
    _s = __salt__.get
    _append_comment(
        ret, summary=(
            'Set upstream: {2}/{1} in {0}'.format(
                wc, rev, origin)))
    # set branch upstreams
    try:
        git_ver = int(
            _s('cmd.run_all')(
                'git --version')['stdout'].split()[-1]
        )
    except (ValueError, TypeError):
        git_ver = 1.8
    if has_no_commits(wc, user=user):
        cret2 = _s('cmd.run_all')(
            'git reset --hard {1}/{0}'.format(
                rev, origin), cwd=wc, runas=user)
        if cret2['retcode'] or cret2['retcode']:
            raise ProjectInitException(
                'Can\'t reset to initial state in {0}'.format(wc))
    if git_ver < 1.8:
        cret2 = _s('cmd.run_all')(
            'git branch --set-upstream master {1}/{0}'.format(
                rev, origin), cwd=wc, runas=user)
        cret1 = _s('cmd.run_all')(
            'git branch --set-upstream {0} {1}/{0}'.format(rev, origin),
            cwd=wc, runas=user)
        if cret2['retcode'] or cret1['retcode']:
            out = splitstrip('{stdout}\n{stderr}'.format(**cret2))
            _append_comment(ret, body=indent(out))
            out = splitstrip('{stdout}\n{stderr}'.format(**cret1))
            _append_comment(ret, body=indent(out))
            raise ProjectInitException(
                'Can\'t set upstreams for {0}'.format(wc))
    else:
        cret = _s('cmd.run_all')(
            'git branch --set-upstream-to={1}/{0}'.format(rev, origin),
            cwd=wc, runas=user)
        if cret['retcode']:
            out = splitstrip('{stdout}\n{stderr}'.format(**cret))
            _append_comment(ret, body=indent(out))
            raise ProjectInitException(
                'Can not set upstream from {2} -> {0}/{1}'.format(
                    origin, rev, wc))
    return ret


def working_copy_in_initial_state(wc, user='root'):
    _s = __salt__.get
    cret = _s('cmd.run_all')(
        'git log --pretty=format:"%h:%s:%an"', cwd=wc, runas=user)
    out = splitstrip('{stdout}\n{stderr}'.format(**cret))
    lines = out.splitlines()
    initial = False
    if len(lines) > 1 and lines[0].count(':') == 2:
        parts = lines[0].split(':')
        if 'makinastates' == parts[2] and 'initial' == parts[1]:
            initial = True
    return initial


def sync_working_copy(user, wc, rev=None, ret=None, origin=None):
    _s = __salt__.get
    if rev is None:
        rev = 'master'
    if origin is None:
        origin = 'origin'
    if not ret:
        ret = _get_ret(wc)
    _append_comment(
        ret, summary=(
            'Synchronise working copy {0} from upstream {2}/{1}'.format(
                wc, rev, origin)))
    initial = working_copy_in_initial_state(wc, user=user)
    nocommits = "fatal: bad default revision 'HEAD'" in _s('cmd.run')(
        'git log', env={'LANG': 'C', 'LC_ALL': 'C'},
        cwd=wc, user=user)
    # the local copy is not yet synchronnized with any repo
    if initial or nocommits or (
        os.listdir(wc) == ['.git']
    ):
        cret = _s('git.reset')(
            wc, '--hard {1}/{0}'.format(rev, origin),
            user=user)
        # in dev mode, no local repo, but we sync it anyway
        # to avoid bugs
        if not cret:
            raise ProjectInitException(
                'Can not sync from {1}@{0} in {2}'.format(
                    origin, rev, wc))
        #else:
        #    _append_comment(
        #        ret, body=indent('Repository {1}: {0}\n'.format(cret, wc)))
    else:
        cret = _s('cmd.run_all')('git pull {1} {0}'.format(rev, origin),
                            cwd=wc, user=user)
        if cret['retcode']:
            # finally try to reset hard
            cret = _s('cmd.run_all')('git reset --hard {1}/{0}'.format(rev, origin),
                                cwd=wc, user=user)
            if cret['retcode']:
                # try to merge a bit but only what's mergeable
                cret = _s('cmd.run_all')(
                    'git merge --ff-only {1}/{0}'.format(rev, origin),
                    cwd=wc, user=user)
                if cret['retcode']:
                    raise ProjectInitException(
                        'Can not sync from {0}/{1} in {2}'.format(
                            origin, rev, wc))
    return ret


def init_pillar_dir(cfg, parent, ret=None):
    salt_settings = __salt__['mc_salt.settings']()
    user, group = cfg['user'], cfg['group']
    files = [os.path.join(parent, 'init.sls')]
    for fil in files:
        # if pillar is empty, create it
        if os.path.exists(fil):
            with open(fil) as fic:
                if fic.read().strip():
                    continue
        template = (
            'salt://makina-states/files/projects/2/pillar/{0}'.format(
                os.path.basename(fil)))
        init_data = _get_filtered_cfg(cfg)
        for k in [a for a in init_data]:
            if k not in [
                "api_version",
            ]:
                del init_data[k]
        defaults = {
            'name': cfg['name'],
            'cfg': yaml.dump(
                {
                    'makina-projects.{name}'.format(
                        **cfg): init_data
                },  width=80, indent=2, default_flow_style=False
            ),
        }
        cret = _state_exec(sfile, 'managed',
                           name=fil, source=template,
                           makedirs=True,
                           defaults=defaults, template='jinja',
                           user=user, group=group, mode='770')
        if not cret['result']:
            raise ProjectInitException(
                'Can\'t create default {0}\n{1}'.format(fil, cret['comment']))
        #else:
        #    _append_comment(ret, body=indent(cret['comment']))


def refresh_files_in_working_copy(name, *args, **kwargs):
    _s = __salt__.get
    cfg = get_configuration(name, *args, **kwargs)
    ret = _get_ret(name, *args, **kwargs)
    _append_comment(
        ret, summary='Verify or initialise some default files')
    user, group = cfg['user'], cfg['group']
    project_root = cfg['project_root']
    salt_root = os.path.join(project_root, '.salt')
    if not os.path.exists(
        os.path.join(project_root, '.salt')
    ):
        raise ProjectInitException('Too early to call me')
    for fil in ['PILLAR.sample']:
        dest = os.path.join(project_root, '.salt', fil)
        if os.path.exists(dest):
            continue
        template = (
            'salt://makina-states/files/projects/{1}/'
            'salt/{0}'.format(fil, cfg['api_version']))
        cret = _state_exec(sfile, 'managed',
                           name=dest,
                           source=template, defaults={},
                           user=user, group=group,
                           makedirs=True,
                           mode='770', template='jinja')
        if not cret['result']:
            raise ProjectInitException(
                'Can\'t create default {0}\n{1}'.format(
                    fil, cret['comment']))
    return ret


def init_salt_dir(cfg, parent, ret=None):
    _s = __salt__.get
    if not ret:
        ret = _get_ret(cfg['name'])
    _append_comment(
        ret, summary='Verify or initialise salt & pillar core files')
    user, group = cfg['user'], cfg['group']
    pillar_root = cfg['pillar_root']
    salt_root = os.path.join(parent, '.salt')
    if not os.path.exists(parent):
        raise ProjectInitException(
            'parent for salt root {0} does not exist'.format(parent))
    cret = _state_exec(sfile, 'directory',
                       salt_root,
                       user=user,
                       group=group,
                       mode='770')
    if not cret['result']:
        raise ProjectInitException(
            'Can\'t manage {0} dir'.format(salt_root))
    #else:
    #    _append_comment(ret, body=indent(cret['comment']))
    files = [os.path.join(salt_root, a)
             for a in os.listdir(salt_root)
             if a.endswith('.sls') and not os.path.isdir(a)]
    if not files:
        for fil in SPECIAL_SLSES + ['PILLAR.sample',
                                    '00_helloworld.sls']:
            template = (
                'salt://makina-states/files/projects/{1}/'
                'salt/{0}'.format(fil, cfg['api_version']))
            cret = _state_exec(sfile, 'managed',
                               name=os.path.join(salt_root, '{0}').format(fil),
                               source=template, defaults={},
                               user=user, group=group,
                               makedirs=True,
                               mode='770', template='jinja')
            if not cret['result']:
                raise ProjectInitException(
                    'Can\'t create default {0}\n{1}'.format(
                        fil, cret['comment']))
            #else:
            #    _append_comment(ret, body=indent(cret['comment']))
    return ret


def init_project(name, *args, **kwargs):
    '''
    See common args to feed the neccessary variables to set a project
    You will need at least:

        - A name
        - A type
        - The pillar git repository url
        - The project & salt git repository url

    '''
    _s = __salt__.get
    cfg = get_configuration(name, *args, **kwargs)
    user, groups, group = cfg['user'], cfg['groups'], cfg['group']
    ret = _get_ret(cfg['name'])
    try:
        init_user_groups(user, groups, ret=ret)
        init_ssh_user_keys(user,
                           failhard=cfg['default_env'] in ['dev'],
                           ret=ret)
        init_project_dirs(cfg, ret=ret)
        project_git_root = cfg['project_git_root']
        pillar_git_root = cfg['pillar_git_root']
        repos = [
            (
                cfg['pillar_root'],
                'master',
                pillar_git_root,
                False,
                False,
                True,
            ),
            (
                cfg['project_root'],
                'master',
                project_git_root,
                True,
                True,
                False,
            ),
        ]
        for wc, rev, localgit, hook, init_salt, init_pillar in repos:
            init_repo(cfg, localgit, user, group, ret=ret,
                      init_salt=init_salt, init_pillar=init_pillar,
                      bare=True)
            if hook:
                sync_hooks(name, localgit, user, group, ret=ret,
                           bare=True, api_version=cfg['api_version'])
            init_repo(cfg, wc, user, group, ret=ret, bare=False)
            for working_copy, remote in [(localgit, wc),
                                         (wc, localgit)]:
                set_git_remote(working_copy, user, remote, ret=ret)
            fetch_last_commits(wc, user, ret=ret)
        # to mutally sync remotes, all repos must be created
        # first, so we need to cut off and reiterate over
        # the same iterables, but in 2 times
        for wc, rev, localgit, hook, init_salt, init_pillar in repos:
            set_upstream(wc, rev, user, ret=ret)
            sync_working_copy(user, wc, rev=rev, ret=ret)
        link(name, *args, **kwargs)
        refresh_files_in_working_copy(name, *args, **kwargs)
    except ProjectInitException, ex:
        trace = traceback.format_exc()
        ret['result'] = False
        _append_comment(ret,
                        summary="{0}".format(ex),
                        color='RED_BOLD',
                        body="{0}{1}{2}".format(
                            _colors('RED'), trace, _colors('ENDC')
                        ))
    if ret['result']:
        set_configuration(cfg['name'], cfg)
        _append_comment(ret, summary="You can now push to",
                        color='RED',
                        body='Pillar: {0}\nProject: {1}'.format(
                            cfg['push_pillar_url'],
                            cfg['push_salt_url']))
    msplitstrip(ret)
    return _filter_ret(ret, cfg['raw_console_return'])


def guarded_step(cfg,
                 step_or_steps,
                 inner_step=False,
                 error_msg=None,
                 rollback=False,
                 *args, **kwargs):
    name = cfg['name']
    ret = _get_ret(name, *args, **kwargs)
    if isinstance(step_or_steps, basestring):
        step_or_steps = [step_or_steps]
    if not step_or_steps:
        return ret
    # only rollback if the minimum to rollback is there
    if rollback and os.path.exists(cfg['project_root']):
        rollback = cfg['default_env'] not in ['dev']
        # XXX: remove me (True)!
        # rollback = True
    if not error_msg:
        error_msg = ''
    step = step_or_steps[0]
    try:
        try:
            for step in step_or_steps:
                set_project(cfg)
                if cfg.get('skip_{0}'.format(step), False):
                    continue
                cret = __salt__['mc_project_{1}.{0}'.format(
                    step, cfg['api_version'])](name, *args, **kwargs)
                _merge_statuses(ret, cret, step=step)
        except ProjectProcedureException, pr:

            # if we are not in an inner step, raise in first place !
            # and do not mark for rollback
            if inner_step:
                cfg['rollback'] = rollback
            ret['result'] = False
            # in non editable modes, set the rollback project flag
            _merge_statuses(ret, pr.salt_ret, step=pr.salt_step)
    except Exception, ex:
        error_msg = (
            'Deployment error: {3}\n'
            'Project {0} failed to deploy and triggered a non managed '
            'exception in step {2}.\n'
            '{1}').format(name, ex, step.capitalize(), step)
        # if we have a non scheduled exception, we leave the system
        # in place for further inspection
        trace = traceback.format_exc()
        ret['result'] = False
        # in non editable modes, set the rollback project flag
        cfg['rollback'] = rollback
        _append_separator(ret)
        _append_comment(
            ret, summary=error_msg.format(name, ex, step.capitalize(), step),
            body=trace, color='RED')
    return ret


def execute_garded_step(name,
                        step_or_steps,
                        inner_step=False,
                        error_msg=None,
                        rollback=False,
                        *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    return guarded_step(cfg, step_or_steps,
                        inner_step=inner_step,
                        error_msg=error_msg,
                        rollback=rollback,
                        *args, **kwargs)


def deploy(name, *args, **kwargs):
    '''Deploy a project

    Only run install step::

        salt-call --local -lall mc_project.deploy <name> only=install

    Only run install & fixperms step::

        salt-call --local -lall mc_project.deploy <name> only=install,fixperms

    Deploy entirely (this is what is run whithin the git hook)::

        salt-call --local -lall mc_project.deploy <name>

    Skip a particular step::

        salt-call mc_project.deploy <name> skip_release_sync=True skip_archive=True skip_notify=True


    '''
    ret = _get_ret(name, *args, **kwargs)
    cfg = get_configuration(name, *args, **kwargs)
    if cfg['skip_deploy']:
        return ret
    # make the deploy_ret dict available in notify sls runners
    # via the __opts__.ms_project.deploy_ret variable
    cfg['deploy_summary'] = None
    cfg['deploy_ret'] = ret
    # in early stages, if something goes wrong, we want/cant do
    # much more that inviting the user to inspect the environment
    # only archive  the minimum to rollback is there
    if os.path.exists(cfg['project_root']):
        guarded_step(cfg, 'archive', ret=ret, *args, **kwargs)
    # okay, if backups are now done and in OK status
    # hand tights for the deployment

    if ret['result']:
        guarded_step(cfg,
                     ['release_sync', 'install',],
                     rollback=True,
                     inner_step=True,
                     ret=ret)
    # if the rollback flag has been raised, just do a rollback
    # only rollback if the minimum to rollback is there
    if ret['result']:
        guarded_step(cfg, 'rotate_archives', ret=ret, *args, **kwargs)
    if cfg['rollback'] and os.path.exists(cfg['project_root']):
        guarded_step(cfg, 'rollback', ret=ret, *args, **kwargs)
    if ret['result']:
        summary = 'Deployment {0} finished successfully for {1}'.format(
            cfg['chrono'], name)
    else:
        summary = 'Deployment {0} failed for {1}'.format(
            cfg['chrono'], name)
    _append_separator(ret)
    _append_comment(ret, summary, color='RED_BOLD')
    cfg['deploy_summary'] = summary
    # notifications should not modify the result status even failed
    result = ret['result']
    msplitstrip(ret)
    guarded_step(cfg, 'fixperms', ret=ret, *args, **kwargs)
    guarded_step(cfg, 'notify', ret=ret, *args, **kwargs)
    ret['result'] = result
    _force_cli_retcode(ret)
    return _filter_ret(ret, cfg['raw_console_return'])


def archive(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    cret = _step_exec(cfg, 'archive')
    return cret


def release_sync(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    iret = init_project(name, *args, **kwargs)
    return iret


def get_executable_slss(path, installer_path, installer):
    def do_filter(sx):
        x = os.path.join(path, sx)
        filtered = True
        if (
            sx in SPECIAL_SLSES
            or (os.path.isdir(x))
            or (not sx.endswith('.sls'))
        ):
            filtered = False
        return filtered
    slses = [a.split('.sls')[0]
             for a in filter(do_filter, os.listdir(path))]
    def sls_sort(a):
        '''
        >>> sorted(['0100_a', '0010_b', '0004_a','100_b',
        ... '0_4', '0_1', '0_2'], key=a)
        ['0004_a', '0010_b', '0100_a', '0_1', '0_2', '0_4', '100_b']
        '''
        return a
    slses.sort(key=sls_sort)
    return slses


def install(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    ret = _get_ret(name, *args, **kwargs)
    if not os.path.exists(cfg['installer_path']):
        raise ProjectInitException(
            'invalid project type or installer directory: {0}/{1}'.format(
                cfg['installer'], cfg['installer_path']))
    cret = None
    slses = get_executable_slss(
        cfg['wired_salt_root'],
        cfg['installer_path'],
        cfg['installer'])
    if not slses:
        raise _stop_proc('No installation slses avalaible for {0}'.format(name),
                         'install', ret)
    for sls in slses:
        cret = _step_exec(cfg, sls)
        _merge_statuses(ret, cret)
    return ret


def run_setup(name, step_name,  *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    cret = _step_exec(cfg, step)
    return cret


def fixperms(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    cret = _step_exec(cfg, 'fixperms')
    return cret


def link_pillar(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    ret = _get_ret(name, *args, **kwargs)
    salt_settings = __salt__['mc_salt.settings']()
    pillar_root = os.path.join(salt_settings['pillarRoot'])
    pillarf = os.path.join(pillar_root, 'top.sls')
    pillar_top = 'makina-projects.{name}'.format(**cfg)
    with open(pillarf) as fpillarf:
        pillars = fpillarf.read()
        if pillar_top not in pillars:
            lines = []
            for line in pillars.splitlines():
                lines.append(line)
                if line == "  '*':":
                    lines.append('    - {0}\n'.format(pillar_top))
            with open(pillarf, 'w') as wpillarf:
                wpillarf.write('\n'.join(lines))
            _append_comment(
                ret, body=indent(
                    'Added to pillar top: {0}'.format(ret['name'])))
    return ret


def unlink_pillar(name, ret=None, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    ret = _get_ret(name, *args, **kwargs)
    salt_settings = __salt__['mc_salt.settings']()
    pillar_root = os.path.join(salt_settings['pillarRoot'])
    pillarf = os.path.join(pillar_root, 'top.sls')
    pillar_top = 'makina-projects.{name}'.format(**cfg)
    with open(pillarf) as fpillarf:
        pillar_top = '- makina-projects.{name}'.format(**cfg)
        pillars = fpillarf.read()
        if pillar_top in pillars:
            lines = []
            for line in pillars.splitlines():
                if line.endswith(pillar_top):
                    continue
                lines.append(line)
            with open(pillarf, 'w') as wpillarf:
                wpillarf.write('\n'.join(lines))
            _append_comment(
                ret, body=indent(
                    'Cleaned pillar top: {0}'.format(ret['name'])))
    if os.path.exists(cfg['wired_pillar_root']):
        remove_path(cfg['wired_pillar_root'])
    return ret


def link(name, *args, **kwargs):
    ret = link_pillar(name, *args, **kwargs)
    return ret


def unlink(name, *args, **kwargs):
    ret = unlink_pillar(name, *args, **kwargs)
    return ret


def rollback(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    ret = _get_ret(name, *args, **kwargs)
    cret = _step_exec(cfg, 'rollback')
    return cret

def rotate_archives(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    ret = _get_ret(name, *args, **kwargs)
    try:
        if os.path.exists(cfg['archives_root']):
            archives = sorted(os.listdir(cfg['archives_root']))
            to_keep = archives[-cfg['keep_archives']:]
            for archive in archives:
                if not archive in to_keep:
                    remove_path(os.path.join(cfg['archives_root'], archive))
        _append_comment( ret, summary=('Archives cleanup done '))
    except Exception, ex:
        trace = traceback.format_exc()
        ret['result'] = False
        _append_comment(
            ret, color='RED_BOLD',
            summary=('Archives cleanup procedure '
                     'failed:\n{0}').format(trace))
    return ret


def notify(name, *args, **kwargs):
    cfg = get_configuration(name, *args, **kwargs)
    cret = _step_exec(cfg, 'notify')
    return cret
#
