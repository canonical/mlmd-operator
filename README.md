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

> WARNING: to correctly perform this migration, you must [backup your data](https://discourse.charmhub.io/t/data-backups-and-restoration-for-ckf/13999#heading--backup-mlmd) first.

1. Remove the relation with requirer charms (e.g. `envoy` and `kfp-metadata-writer`)

```
juju remove-relation envoy mlmd
juju remove-relation kfp-metadata-writer mlmd
```

2. Remove the `mlmd` application.

> WARNING: this will wipe out the storage attached to the `mlmd` charm, therefore, the database
that this charm handles. It is important you perform a [data backup](https://discourse.charmhub.io/t/data-backups-and-restoration-for-ckf/13999#heading--backup-mlmd) before
running this step.

```
juju remove-application mlmd --destroy-storage
```

3. Deploy `mlmd` from a newer channel

```
juju deploy mlmd --channel <channel-greater-than-1.14/stable> --trust
```

4. [Restore your data](https://discourse.charmhub.io/t/data-backups-and-restoration-for-ckf/13999#heading--restore-mlmd).

5. Relate to the requirer charms

> NOTE: `mlmd>1.14/stable` can only be related to `envoy>2.0/stable` and `kfp-metadata-writer>2.0/stable`

```
juju relate envoy mlmd
juju relate kfp-metadata-writer mlmd
```
