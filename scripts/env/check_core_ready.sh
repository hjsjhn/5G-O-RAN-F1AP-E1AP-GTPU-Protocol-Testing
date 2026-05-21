#!/usr/bin/env bash
# Verify that Open5GS and srsRAN split control-plane links are up.
set -euo pipefail

required_containers=(
  mongo nrf scp ausf udr udm pcf bsf nssf amf smf upf webui
  srsran_cu_cp srsran_cu_up srsran_du
)

for container in "${required_containers[@]}"; do
  if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    echo "FAIL: container not running: $container" >&2
    exit 1
  fi
done

docker exec smf grep -q 'SMF initialize...done' /open5gs/install/var/log/open5gs/smf.log
docker exec smf grep -q 'PFCP associated \[172.22.0.8\]:8805' /open5gs/install/var/log/open5gs/smf.log
docker exec upf grep -q 'PFCP associated \[172.22.0.7\]:8805' /open5gs/install/var/log/open5gs/upf.log
docker exec amf grep -q 'gNB-N2 accepted\[10.53.1.4\]' /open5gs/install/var/log/open5gs/amf.log
docker exec srsran_du grep -q 'F1 Setup: Procedure completed successfully' /tmp/du.log

docker exec srsran_cu_cp ss -n -A sctp | grep -q '10.53.1.2:38412'
docker exec srsran_cu_cp ss -n -A sctp | grep -q '10.53.1.5:'
docker exec srsran_cu_cp ss -n -A sctp | grep -q '10.53.1.6:'

echo "OK: 5G Core is up; SMF/UPF PFCP is associated; NGAP/E1AP/F1AP SCTP links are established."
