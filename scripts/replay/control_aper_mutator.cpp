#include "srsran/adt/byte_buffer.h"
#include "srsran/asn1/e1ap/e1ap.h"
#include "srsran/asn1/e1ap/e1ap_pdu_contents.h"
#include "srsran/asn1/f1ap/f1ap.h"
#include "srsran/asn1/f1ap/f1ap_pdu_contents_ue.h"
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <type_traits>
#include <vector>

using namespace asn1;
using namespace srsran;

static std::vector<uint8_t> parse_hex(const std::string& value)
{
  if (value.size() % 2 != 0) {
    std::cerr << "payload hex length must be even\n";
    std::exit(2);
  }
  std::vector<uint8_t> bytes;
  bytes.reserve(value.size() / 2);
  for (size_t i = 0; i < value.size(); i += 2) {
    bytes.push_back(static_cast<uint8_t>(std::stoul(value.substr(i, 2), nullptr, 16)));
  }
  return bytes;
}

static std::string hex_string(const byte_buffer& buffer)
{
  std::ostringstream stream;
  for (uint8_t octet : buffer) {
    stream << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(octet);
  }
  return stream.str();
}

static uint64_t mutate_f1ap(asn1::f1ap::f1ap_pdu_c& pdu, const std::string& message, const std::string& field, uint64_t value)
{
  if (pdu.type().value != asn1::f1ap::f1ap_pdu_c::types_opts::init_msg) {
    std::cerr << "F1AP mutation requires an initiating message\n";
    std::exit(3);
  }
  if (field != "GNB_CU_UE_F1AP_ID") {
    std::cerr << "unsupported F1AP mutation field: " << field << "\n";
    std::exit(4);
  }
  if (message == "UEContextSetupRequest") {
    auto& ies = *pdu.init_msg().value.ue_context_setup_request();
    auto  old = ies.gnb_cu_ue_f1ap_id;
    ies.gnb_cu_ue_f1ap_id = value;
    return old;
  }
  if (message == "UEContextModificationRequest") {
    auto& ies = *pdu.init_msg().value.ue_context_mod_request();
    auto  old = ies.gnb_cu_ue_f1ap_id;
    ies.gnb_cu_ue_f1ap_id = value;
    return old;
  }
  if (message == "UEContextReleaseCommand") {
    auto& ies = *pdu.init_msg().value.ue_context_release_cmd();
    auto  old = ies.gnb_cu_ue_f1ap_id;
    ies.gnb_cu_ue_f1ap_id = value;
    return old;
  }
  std::cerr << "unsupported F1AP message: " << message << "\n";
  std::exit(5);
}

static uint64_t mutate_e1ap(asn1::e1ap::e1ap_pdu_c& pdu, const std::string& message, const std::string& field, uint64_t value)
{
  if (pdu.type().value != asn1::e1ap::e1ap_pdu_c::types_opts::init_msg) {
    std::cerr << "E1AP mutation requires an initiating message\n";
    std::exit(6);
  }
  if (field != "GNB_CU_CP_UE_E1AP_ID") {
    std::cerr << "unsupported E1AP mutation field: " << field << "\n";
    std::exit(7);
  }
  if (message == "BearerContextSetupRequest") {
    auto& ies = *pdu.init_msg().value.bearer_context_setup_request();
    auto  old = ies.gnb_cu_cp_ue_e1ap_id;
    ies.gnb_cu_cp_ue_e1ap_id = value;
    return old;
  }
  if (message == "BearerContextModificationRequest") {
    auto& ies = *pdu.init_msg().value.bearer_context_mod_request();
    auto  old = ies.gnb_cu_cp_ue_e1ap_id;
    ies.gnb_cu_cp_ue_e1ap_id = value;
    return old;
  }
  if (message == "BearerContextReleaseCommand") {
    auto& ies = *pdu.init_msg().value.bearer_context_release_cmd();
    auto  old = ies.gnb_cu_cp_ue_e1ap_id;
    ies.gnb_cu_cp_ue_e1ap_id = value;
    return old;
  }
  std::cerr << "unsupported E1AP message: " << message << "\n";
  std::exit(8);
}

template <typename Pdu>
static byte_buffer decode_mutate_encode(
    const std::vector<uint8_t>& bytes, const std::string& protocol, const std::string& message, const std::string& field, uint64_t value, uint64_t& old)
{
  auto input = byte_buffer::create(bytes).value();
  cbit_ref reader(input);
  Pdu      pdu;
  if (pdu.unpack(reader) != SRSASN_SUCCESS) {
    std::cerr << protocol << " APER decode failed\n";
    std::exit(9);
  }

  if constexpr (std::is_same_v<Pdu, asn1::f1ap::f1ap_pdu_c>) {
    old = mutate_f1ap(pdu, message, field, value);
  } else {
    old = mutate_e1ap(pdu, message, field, value);
  }

  byte_buffer output;
  bit_ref     writer(output);
  if (pdu.pack(writer) != SRSASN_SUCCESS) {
    std::cerr << protocol << " APER encode failed\n";
    std::exit(10);
  }

  cbit_ref verify_reader(output);
  Pdu      verify_pdu;
  if (verify_pdu.unpack(verify_reader) != SRSASN_SUCCESS) {
    std::cerr << protocol << " re-encoded APER verification decode failed\n";
    std::exit(11);
  }
  return output;
}

int main(int argc, char** argv)
{
  if (argc != 6) {
    std::cerr << "usage: control_aper_mutator PROTOCOL MESSAGE PAYLOAD_HEX FIELD VALUE\n";
    return 1;
  }
  const std::string protocol = argv[1];
  const std::string message  = argv[2];
  const std::string payload  = argv[3];
  const std::string field    = argv[4];
  const uint64_t    value    = std::stoull(argv[5], nullptr, 0);
  uint64_t          old      = 0;
  byte_buffer       output;

  if (protocol == "F1AP") {
    output = decode_mutate_encode<asn1::f1ap::f1ap_pdu_c>(parse_hex(payload), protocol, message, field, value, old);
  } else if (protocol == "E1AP") {
    output = decode_mutate_encode<asn1::e1ap::e1ap_pdu_c>(parse_hex(payload), protocol, message, field, value, old);
  } else {
    std::cerr << "unsupported protocol: " << protocol << "\n";
    return 12;
  }

  std::cout << "{\"field\":\"" << field << "\",\"before\":" << old << ",\"after\":" << value
            << ",\"payload_hex\":\"" << hex_string(output) << "\"}\n";
  return 0;
}
