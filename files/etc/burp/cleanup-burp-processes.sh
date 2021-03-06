#!/usr/bin/env bash
PS="ps"
is_lxc() {
    echo  "$(cat -e /proc/1/environ |grep container=lxc|wc -l|sed -e "s/ //g")"
}
filter_host_pids() {
    if [ "x$(is_lxc)" != "x0" ];then
        echo "${@}"
    else
        for pid in ${@};do
            if [ "x$(grep -q lxc /proc/${pid}/cgroup 2>/dev/null;echo "${?}")" != "x0" ];then
                 echo ${pid}
             fi
         done
    fi
}
burp_client() {
    filter_host_pids $(${PS} aux|grep burp|grep -- "-a t"|grep -v grep|awk '{print $2}')|wc -w|sed -e "s/ //g"
}
ps_etime() {
    ${PS} -eo pid,comm,etime,args | perl -ane '@t=reverse(split(/[:-]/, $F[2])); $s=$t[0]+$t[1]*60+$t[2]*3600+$t[3]*86400;$cmd=join(" ", @F[3..$#F]);print "$F[0]\t$s\t$F[1]\t$F[2]\t$cmd\n"'
}
kill_old_syncs() {
    # kill all stale synchronnise code jobs
    ps_etime|sort -n -k2|grep burp|grep -- "-a t"|grep -v grep|while read psline;
    do
        seconds="$(echo "$psline"|awk '{print $2}')"
        pid="$(filter_host_pids $(echo $psline|awk '{print $1}'))"
        # 8 minutes
        if [ "x${pid}" != "x" ] && [ "${seconds}" -gt "72000" ];then
            echo "Something was wrong with last backup, killing old sync processes: $pid"
            echo "${psline}"
            kill -9 "${pid}"
            todo="y"
        fi
    done
    lines="$(filter_host_pids $(ps aux|grep burp|grep -- '-a t'|awk '{print $2}')|wc -l|sed 's/ +//g')"
    if [ "x${lines}" = "x0" ];then
        if [ -f /var/run/burp.client.pid ];then
            todo="y"
            rm -f /var/run/burp.client.pid
        fi
    fi
}

todo=""
kill_old_syncs
# trigger a backup try if we were killed
if [ "x${todo}" != "x" ];then
    burp -a t
fi
# vim:set et sts=4 ts=4 tw=0:
