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
SED_DEPLOY=`echo "$DEPLOY" | sed -e "s_/_\\\\\\\\/_g"`
SED_SOURCE=`echo "$SOURCE" | sed -e "s_/_\\\\\\\\/_g"`

echo "using $DEPLOY"
echo "from $SOURCE"

echo "generating directory structure"
for d in run logs static profiles tmp
do
    mkdir $DEPLOY/$d
done
echo "copying configuration files"
for d in mongrel2 pyskillweb
do
    mkdir $DEPLOY/profiles/$d
    for f in restart depends pid_file run
    do
        FILE=$SOURCE/config/${d}/${f}
        DEST=$DEPLOY/profiles/$d/$f
        if [ -a $FILE ]
        then
            cat $FILE | sed -e "s/\${DEPLOY}/$SED_DEPLOY/g" \
                            -e "s/\${SOURCE}/$SED_SOURCE/g" > $DEST
        else
            touch $DEST
        fi
    done
    echo "setting $DEST as executable by user"
    chmod u+x $DEST
done

# make run.log owned by user to avoid procer bug that fails to start process
# if owned by root (github issue #107)
touch $DEPLOY/profiles/run.log

echo "generating mongrel2 configuration database"
cat $SOURCE/config/mongrel2.conf | sed -e "s/\${DEPLOY}/$SED_DEPLOY/g" \
                                       -e "s/\${SOURCE}/$SED_SOURCE/g" > $DEPLOY/mongrel2.conf
m2sh load --config $DEPLOY/mongrel2.conf --db $DEPLOY/config.sqlite

echo "setting mongrel2 to run as root"
sudo chown root:root $DEPLOY/profiles/mongrel2

echo "creating procer script"
cp $SOURCE/config/go $DEPLOY
cat $SOURCE/config/update | sed -e "s/\${DEPLOY}/$SED_DEPLOY/g" \
                                -e "s/\${SOURCE}/$SED_SOURCE/g" > $DEPLOY/update
chmod u+x $DEPLOY/update

echo "copying static files"
$DEPLOY/update

echo
tree $DEPLOY
echo
