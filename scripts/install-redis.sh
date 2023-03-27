#! /bin/bash

redis_version=7.0.10
redis_port=6379

wget https://github.com/redis/redis/archive/$redis_version.tar.gz --no-check-certificate
tar -xzvf $redis_version.tar.gz

mkdir -p /etc/redis /var/redis/$redis_port

cd redis-$redis_version && make && make install
cp redis.conf /etc/redis/$redis_port.conf && cp utils/redis_init_script /etc/init.d/redis_$redis_port

sed -i "s/daemonize no/daemonize yes/g" /etc/redis/$redis_port.conf
sed -i "s#logfile \"\"#logfile \"/var/log/redis_$redis_port.log\"#g" /etc/redis/$redis_port.conf
sed -i "s#dir ./#dir /var/redis/$redis_port#g" /etc/redis/$redis_port.conf

update-rc.d redis_$redis_port defaults

# start the redis server
/etc/init.d/redis_$redis_port start

redis-cli ping || echo 'Unable to start Redis'
