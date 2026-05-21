#!/usr/bin/env bash
# Provision the default UE subscriber in Open5GS MongoDB.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/docker/compose/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run scripts/env/start_env.sh first or copy docker/compose/.env.example to .env." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${UE1_IMSI:?missing UE1_IMSI}"
: "${UE1_KI:?missing UE1_KI}"
: "${UE1_OP:?missing UE1_OP}"
: "${UE1_AMF:?missing UE1_AMF}"

if ! docker ps --format '{{.Names}}' | grep -q '^mongo$'; then
  echo "MongoDB container is not running. Start the environment first." >&2
  exit 1
fi

docker exec mongo mongosh --quiet --eval "
const imsi = '$UE1_IMSI';
const sub = {
  imsi,
  msisdn: [],
  imeisv: [],
  mme_host: [],
  mm_realm: [],
  purge_flag: [],
  subscribed_rau_tau_timer: 12,
  network_access_mode: 0,
  subscriber_status: 0,
  operator_determined_barring: 0,
  access_restriction_data: 32,
  slice: [{
    sst: 1,
    default_indicator: true,
    session: [{
      name: 'internet',
      type: 3,
      pcc_rule: [],
      ambr: { uplink: { value: 1000000000, unit: 0 }, downlink: { value: 1000000000, unit: 0 } },
      qos: { index: 9, arp: { priority_level: 8, pre_emption_capability: 1, pre_emption_vulnerability: 2 } }
    }, {
      name: 'ims',
      type: 3,
      pcc_rule: [],
      ambr: { uplink: { value: 1000000000, unit: 0 }, downlink: { value: 1000000000, unit: 0 } },
      qos: { index: 5, arp: { priority_level: 8, pre_emption_capability: 1, pre_emption_vulnerability: 2 } }
    }]
  }],
  ambr: { uplink: { value: 1000000000, unit: 0 }, downlink: { value: 1000000000, unit: 0 } },
  security: { k: '$UE1_KI', amf: '$UE1_AMF', op: '$UE1_OP', opc: null },
  schema_version: 1,
  __v: 0
};
db.getSiblingDB('open5gs').subscribers.replaceOne({ imsi }, sub, { upsert: true });
db.getSiblingDB('open5gs').subscribers.find({ imsi }, { imsi: 1, security: 1, slice: 1 }).toArray();
"
