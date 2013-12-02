#!/usr/bin/env bash
# Reset all directories/files perms in subdirectories
python <<EOF
import os
import grp
import stat
import pwd
import traceback

{% if msr is defined %}
m = '{{msr}}'
{% else %}
m = '/srv/salt/makina-states'
{% endif %}
excludes = [
    '.git',
    os.path.join(m , 'lib'),
    os.path.join(m , 'bin'),
    os.path.join(m , 'eggs'),
    os.path.join(m , 'develop-eggs'),
    os.path.join(m , 'parts'),
]
pexcludes = [
{% if excludes is defined %}
{% for i in excludes %}
    '{{i}}',
{% endfor %}
{% endif %}
]


{% if reset_user is defined %}
user = "{{reset_user}}"
{% else %}
user = "{{user}}"
{% endif %}
try:
    uid = int(user)
except Exception:
    uid = int(pwd.getpwnam(user).pw_uid)

{% if reset_group is defined %}
group = "{{reset_group}}"
{% else %}
group = "{{group}}"
{% endif %}
try:
    gid = int(group)
except Exception:
    gid = int(grp.getgrnam(group).gr_gid)

fmode = "0%s" % int("{{fmode}}")
dmode = "0%s" % int("{{dmode}}")


def lazy_chmod_path(path, mode):
    try:
        st = os.stat(path)
        if eval(mode) != stat.S_IMODE(st.st_mode):
            try:
                eval('os.chmod(path, %s)' % mode)
            except Exception:
                print 'Reset failed for %s (%s)' % (path, mode)
                print traceback.format_exc()
    except Exception:
        print 'Reset(o) failed for %s (%s)' % (path, mode)
        print traceback.format_exc()


def lazy_chown_path(path, uid, gid):
    try:
        st = os.stat(path)
        if st.st_uid != uid or st.st_gid != gid:
            try:
                os.chown(path, uid, gid)
            except:
                print 'Reset failed for %s, %s, %s' % (path, uid, gid)
                print traceback.format_exc()
    except Exception:
        print 'Reset(o) failed for %s, %s, %s' % (path, uid, gid)
        print traceback.format_exc()

def lazy_chmod_chown(path, mode, uid, gid):
    lazy_chmod_path(path, mode)
    lazy_chown_path(path, uid, gid)


def to_skip(i):
    stop = False
    if os.path.islink(i):
        # inner dir and files will be excluded too
        pexcludes.append(i)
        stop=True
    else:
        for p in pexcludes:
            if p in i:
                stop = True
                break
    return stop


def reset(p):
    print "Path: %s" % p
    print "Directories: %s" % dmode
    print "Files: %s" % fmode
    print "User:Group: %s:%s\n\n" % (user, group)
    if not os.path.exists(p):
        print "\n\nWARNING: %s does not exist\n\n" % p
        return
    for root, dirs, files in os.walk(p):
        curdir = root
        if to_skip(curdir):
            continue
        try:
            st = os.stat(curdir)
            lazy_chmod_chown(curdir, dmode, uid, gid)
            for item in files:
                i = os.path.join(root, item)
                if to_skip(i): continue
                lazy_chmod_chown(i, fmode, uid, gid)
        except Exception:
            print traceback.format_exc()
            print 'reset failed for %s' % curdir

{% for pt in reset_paths %}
reset('{{pt}}')
{% endfor %}
EOF
exit $?
