#!/usr/bin/env bash
set -eux
MODEL=$1
echo "MODEL=$MODEL"
# Remove the ml_metadata/proto directory before executing the next lines so
# when the script is retried, it doesn't exit because the directory already exists
rm -rf ml_metadata/proto
wget https://raw.githubusercontent.com/google/ml-metadata/master/ml_metadata/proto/metadata_store.proto
wget https://raw.githubusercontent.com/google/ml-metadata/master/ml_metadata/proto/metadata_store_service.proto
wget -O- https://github.com/fullstorydev/grpcurl/releases/download/v1.8.0/grpcurl_1.8.0_linux_x86_64.tar.gz | tar -xzv
mkdir -p ml_metadata/proto/
mv metadata_store.proto ml_metadata/proto/
SERVICE=$(kubectl get services/metadata-grpc-service -n $MODEL -oyaml | yq e .spec.clusterIP -)
./grpcurl -v --proto=metadata_store_service.proto --plaintext $SERVICE:8080 ml_metadata.MetadataStoreService/GetArtifacts
