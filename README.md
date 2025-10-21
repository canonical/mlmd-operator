## ML Metadata Operator

### Overview
This charm encompasses the Kubernetes Python operator for ML Metadata (see
[CharmHub](https://charmhub.io/?q=mlmd)).

The ML Metadata operator is a Python script that wraps the latest released version of ML
Metadata, providing lifecycle management and handling events such as install, upgrade,
integrate, and remove.

## Install

To install ML Metadata, run:

    juju deploy mlmd

For more information, see https://juju.is/docs

## Upgrade

This action can be performed with:

```
juju refresh mlmd --channel <desired-channel>
```

#### Upgrading from `mlmd<=1.14/stable`

> WARNING: you need to backup the data from 1.14 and restore them. Otherwise there will be data loss!

**1. Remove the relation with requirer charms (e.g. `envoy` and `kfp-metadata-writer`)**

```
juju remove-relation envoy mlmd
juju remove-relation kfp-metadata-writer mlmd
```

**2. Backup MLMD with `kubectl`**

First scale down the `kfp-metadata-writer`, which could write data to MLMD.
```bash
juju scale-application kfp-metadata-writer 0
```

Create a backup of the SQLite DB
```bash
MLMD_POD="mlmd-0"
MLMD_CONTAINER="mlmd"
MLMD_BACKUP=mlmd-$(date -d "today" +"%Y-%m-%d-%H-%M").dump.gz

# install sqlite sdk
kubectl exec -n kubeflow $MLMD_POD -c $MLMD_CONTAINER -- \
    /bin/bash -c "apt update && apt install sqlite3 -y"

# create database dump
kubectl exec -n kubeflow $MLMD_POD -c $MLMD_CONTAINER -- \
    /bin/bash -c \
    "sqlite3 /data/mlmd.db .dump | gzip -c >/tmp/$MLMD_BACKUP"
```

**3. Copy the backup data locally**
```bash
kubectl cp -n kubeflow -c $MLMD_CONTAINER \
    $MLMD_POD:/tmp/$MLMD_BACKUP \
    ./$MLMD_BACKUP
```

**4. Remove the `mlmd` application.**

> WARNING: This will delete the application and all data with it. Make sure you've followed
> The above instructions correctly.

```
juju remove-application mlmd --destroy-storage
```

**5. Deploy `mlmd` from a newer channel**

```
juju deploy mlmd --channel ckf-1.9 --trust
```

**6. Restore backed up data**

Restore the copied data and restart `kfp-metadata-writer`
```bash
# The new MLMD charm from ckf-1.9 channel and onwards is using a different container name
MLMD_POD="mlmd-0"
MLMD_CONTAINER="mlmd-grpc-server"

# install the sqlite sdk
kubectl exec -n kubeflow $MLMD_POD -c $MLMD_CONTAINER -- \
    /bin/bash -c "apt update && apt install sqlite3 -y"

# copy the dump file to the container
kubectl cp -n kubeflow -c $MLMD_CONTAINER \
    $MLMD_BACKUP \
    $MLMD_POD:/tmp/$MLMD_BACKUP

# move current database to tmp dir
kubectl exec -n kubeflow $MLMD_POD -c $MLMD_CONTAINER -- \
    /bin/bash -c "mv /data/mlmd.db /tmp/mlmd.current"

# restore the database from dump file
kubectl exec -n kubeflow $MLMD_POD -c $MLMD_CONTAINER -- \
    /bin/bash -c "zcat /tmp/$MLMD_BACKUP | sqlite3 /data/mlmd.db"
```

And finally start again the `kfp-metadata-writer`
```bash
juju scale-application kfp-metadata-writer 1
```

**7. Relate to the requirer charms**

```
juju relate envoy mlmd
juju relate kfp-metadata-writer mlmd
```
