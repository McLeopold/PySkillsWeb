#!/bin/sh
set -e

SOURCE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ $1 ]
then
    DEPLOY=$PWD/$1
    mkdir $DEPLOY
else
    DEPLOY=$PWD
fi
echo "using $DEPLOY"
echo "from $SOURCE"

echo "generating directory structure"
for d in run logs static profiles do
    mkdir $DEPLOY/$d
done
for d in mongrel2 pyskillweb do
    mkdir $DEPLOY/profiles/$d
done

echo "copying configuration files"
for p in $DEPLOY/profiles/*
do
    for f in run restart depends pid_file
    do
        FILE=$SOURCE/config/${p}/${f}
        DEST=$DEPLOY/profiles/$p/$f
        if [ -a $FILE ]
        then
            SED_DEPLOY=`echo "$DEPLOY" | sed -e "s_/_\\\\\\\\/_g"`
            SED_SOURCE=`echo "$SOURCE" | sed -e "s_/_\\\\\\\\/_g"`
            cat $FILE | sed -e "s/\${DEPLOY}/$SED_DEPLOY/g" \
                            -e "s/\${SOURCE}/$SED_SOURCE/g" > $DEST
        else
            touch $DEST
        fi
    done
done

echo "generating mongrel2 configuration database"
cp $SOURCE/mongrel2.conf $DEPLOY/mongrel2.conf
m2sh load --config $DEPLOY/mongrel2.conf --db $DEPLOY/config.sqlite

echo "setting mongrel2 to run as root"
sudo chown root:root $DEPLOY/profiles/mongrel2

tree $DEPLOY

