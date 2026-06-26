#include "srsran/adt/byte_buffer.h"
#include "srsran/asn1/e1ap/e1ap.h"
#include "srsran/asn1/e1ap/e1ap_pdu_contents.h"
#include "srsran/asn1/f1ap/common.h"
#include "srsran/asn1/f1ap/f1ap.h"
#include "srsran/asn1/f1ap/f1ap_pdu_contents.h"
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <string>

using namespace asn1;
using namespace srsran;

static std::map<std::string, std::string> parse_fields(int argc, char** argv)
{
  std::map<std::string, std::string> fields;
  for (int i = 3; i < argc; ++i) {
    std::string argument = argv[i];
    auto        separator = argument.find('=');
    if (separator == std::string::npos || separator == 0) {
      std::cerr << "field arguments must use key=value syntax\n";
      std::exit(2);
    }
    auto key = argument.substr(0, separator);
    if (!fields.emplace(key, argument.substr(separator + 1)).second) {
      std::cerr << "duplicate field: " << key << "\n";
      std::exit(3);
    }
  }
  return fields;
}

static const std::string& required(const std::map<std::string, std::string>& fields, const std::string& name)
{
  auto value = fields.find(name);
  if (value == fields.end() || value->second.empty()) {
    std::cerr << "missing required field: " << name << "\n";
    std::exit(4);
  }
  return value->second;
}

static uint64_t number(const std::map<std::string, std::string>& fields, const std::string& name)
{
  const auto& text = required(fields, name);
  size_t      consumed = 0;
  uint64_t    value    = std::stoull(text, &consumed, 0);
  if (consumed != text.size()) {
    std::cerr << "invalid integer field: " << name << "\n";
    std::exit(5);
  }
  return value;
}

static std::string hex_string(const byte_buffer& buffer)
{
  std::ostringstream stream;
  for (uint8_t octet : buffer) {
    stream << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(octet);
  }
  return stream.str();
}

template <typename Pdu>
static byte_buffer pack_verified(Pdu& pdu)
{
  byte_buffer payload;
  bit_ref     writer(payload);
  if (pdu.pack(writer) != SRSASN_SUCCESS) {
    std::cerr << "APER pack failed\n";
    std::exit(6);
  }
  cbit_ref reader(payload);
  Pdu     decoded;
  if (decoded.unpack(reader) != SRSASN_SUCCESS) {
    std::cerr << "APER verification decode failed\n";
    std::exit(7);
  }
  return payload;
}

static asn1::f1ap::f1ap_pdu_c make_f1_setup(const std::map<std::string, std::string>& fields)
{
  asn1::f1ap::f1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_F1AP_ID_F1_SETUP);
  auto& request                = pdu.init_msg().value.f1_setup_request();
  request->transaction_id      = number(fields, "transaction_id");
  request->gnb_du_id           = number(fields, "gnb_du_id");
  request->gnb_du_name_present = true;
  request->gnb_du_name.from_string(required(fields, "gnb_du_name"));
  request->gnb_du_rrc_version.latest_rrc_version.from_number(number(fields, "rrc_version"));
  request->gnb_du_served_cells_list_present = true;

  protocol_ie_single_container_s<asn1::f1ap::gnb_du_served_cells_item_ies_o> container;
  container.set_item(ASN1_F1AP_ID_GNB_DU_SERVED_CELLS_ITEM);
  auto& item = container.value().gnb_du_served_cells_item();
  item.served_cell_info.nr_cgi.plmn_id.from_string(required(fields, "plmn_id"));
  item.served_cell_info.nr_cgi.nr_cell_id.from_number(number(fields, "nr_cell_id"));
  item.served_cell_info.nr_pci              = number(fields, "nr_pci");
  item.served_cell_info.five_gs_tac_present = true;
  item.served_cell_info.five_gs_tac.from_number(number(fields, "tac"));
  asn1::f1ap::served_plmns_item_s plmn;
  plmn.plmn_id.from_string(required(fields, "plmn_id"));
  item.served_cell_info.served_plmns.push_back(plmn);
  item.served_cell_info.nr_mode_info.set_tdd();
  item.served_cell_info.nr_mode_info.tdd().nr_freq_info.nr_arfcn = number(fields, "nr_arfcn");
  asn1::f1ap::freq_band_nr_item_s band;
  band.freq_band_ind_nr = number(fields, "freq_band");
  item.served_cell_info.nr_mode_info.tdd().nr_freq_info.freq_band_list_nr.push_back(band);
  if (required(fields, "nr_scs") != "scs30" || required(fields, "nr_nrb") != "nrb51") {
    std::cerr << "only nr_scs=scs30 and nr_nrb=nrb51 are supported by this testcase generator\n";
    std::exit(8);
  }
  item.served_cell_info.nr_mode_info.tdd().tx_bw.nr_scs.value = asn1::f1ap::nr_scs_opts::scs30;
  item.served_cell_info.nr_mode_info.tdd().tx_bw.nr_nrb.value = asn1::f1ap::nr_nrb_opts::nrb51;
  item.served_cell_info.meas_timing_cfg.from_string(required(fields, "meas_timing_cfg"));
  item.gnb_du_sys_info_present = true;
  item.gnb_du_sys_info.mib_msg.from_string(required(fields, "mib_hex"));
  item.gnb_du_sys_info.sib1_msg.from_string(required(fields, "sib1_hex"));
  request->gnb_du_served_cells_list.push_back(container);
  return pdu;
}

static asn1::f1ap::f1ap_pdu_c make_f1_cfg_update(const std::map<std::string, std::string>& fields)
{
  asn1::f1ap::f1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_F1AP_ID_GNB_DU_CFG_UPD);
  auto& request              = pdu.init_msg().value.gnb_du_cfg_upd();
  request->transaction_id    = number(fields, "transaction_id");
  request->gnb_du_id_present = true;
  request->gnb_du_id         = number(fields, "gnb_du_id");
  return pdu;
}

static asn1::f1ap::f1ap_pdu_c make_f1_reset(const std::map<std::string, std::string>& fields)
{
  if (required(fields, "cause") != "misc_unspecified" || required(fields, "reset_scope") != "f1_interface") {
    std::cerr << "unsupported F1 Reset cause or scope\n";
    std::exit(9);
  }
  asn1::f1ap::f1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_F1AP_ID_RESET);
  auto& request           = pdu.init_msg().value.reset();
  request->transaction_id = number(fields, "transaction_id");
  request->cause.set_misc().value = asn1::f1ap::cause_misc_opts::unspecified;
  request->reset_type.set_f1_interface().value = asn1::f1ap::reset_all_opts::reset_all;
  return pdu;
}

static asn1::e1ap::e1ap_pdu_c make_e1_setup(const std::map<std::string, std::string>& fields)
{
  if (required(fields, "cn_support") != "5gc") {
    std::cerr << "only cn_support=5gc is supported\n";
    std::exit(10);
  }
  asn1::e1ap::e1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_E1AP_ID_GNB_CU_UP_E1_SETUP);
  auto& request                   = pdu.init_msg().value.gnb_cu_up_e1_setup_request();
  request->transaction_id         = number(fields, "transaction_id");
  request->gnb_cu_up_id           = number(fields, "gnb_cu_up_id");
  request->gnb_cu_up_name_present = true;
  request->gnb_cu_up_name.from_string(required(fields, "gnb_cu_up_name"));
  request->cn_support.value = asn1::e1ap::cn_support_opts::c_5gc;
  asn1::e1ap::supported_plmns_item_s plmn;
  plmn.plmn_id.from_string(required(fields, "supported_plmn"));
  request->supported_plmns.push_back(plmn);
  return pdu;
}

static asn1::e1ap::e1ap_pdu_c make_e1_cfg_update(const std::map<std::string, std::string>& fields)
{
  asn1::e1ap::e1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_E1AP_ID_GNB_CU_UP_CFG_UPD);
  auto& request                    = pdu.init_msg().value.gnb_cu_up_cfg_upd();
  request->transaction_id          = number(fields, "transaction_id");
  request->gnb_cu_up_id            = number(fields, "gnb_cu_up_id");
  request->supported_plmns_present = true;
  asn1::e1ap::supported_plmns_item_s plmn;
  plmn.plmn_id.from_string(required(fields, "supported_plmn"));
  request->supported_plmns.push_back(plmn);
  return pdu;
}

static asn1::e1ap::e1ap_pdu_c make_e1_reset(const std::map<std::string, std::string>& fields)
{
  if (required(fields, "cause") != "misc_unspecified" || required(fields, "reset_scope") != "e1_interface") {
    std::cerr << "unsupported E1 Reset cause or scope\n";
    std::exit(11);
  }
  asn1::e1ap::e1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_E1AP_ID_RESET);
  auto& request           = pdu.init_msg().value.reset();
  request->transaction_id = number(fields, "transaction_id");
  request->cause.set_misc().value = asn1::e1ap::cause_misc_opts::unspecified;
  request->reset_type.set_e1_interface();
  return pdu;
}

int main(int argc, char** argv)
{
  if (argc < 4) {
    std::cerr << "usage: control_peer_payload_generator PROTOCOL MESSAGE key=value...\n";
    return 1;
  }
  const std::string protocol = argv[1];
  const std::string message  = argv[2];
  const auto        fields   = parse_fields(argc, argv);
  byte_buffer       payload;
  if (protocol == "F1AP" && message == "F1SetupRequest") {
    auto pdu = make_f1_setup(fields);
    payload  = pack_verified(pdu);
  } else if (protocol == "F1AP" && message == "GNBDUConfigurationUpdate") {
    auto pdu = make_f1_cfg_update(fields);
    payload  = pack_verified(pdu);
  } else if (protocol == "F1AP" && message == "Reset") {
    auto pdu = make_f1_reset(fields);
    payload  = pack_verified(pdu);
  } else if (protocol == "E1AP" && message == "GNB-CU-UP-E1SetupRequest") {
    auto pdu = make_e1_setup(fields);
    payload  = pack_verified(pdu);
  } else if (protocol == "E1AP" && message == "GNB-CU-UP-ConfigurationUpdate") {
    auto pdu = make_e1_cfg_update(fields);
    payload  = pack_verified(pdu);
  } else if (protocol == "E1AP" && message == "Reset") {
    auto pdu = make_e1_reset(fields);
    payload  = pack_verified(pdu);
  } else {
    std::cerr << "unsupported protocol/message: " << protocol << "/" << message << "\n";
    return 12;
  }
  std::cout << "{\"protocol\":\"" << protocol << "\",\"message\":\"" << message << "\",\"transaction_id\":"
            << number(fields, "transaction_id") << ",\"payload_hex\":\"" << hex_string(payload) << "\"}\n";
  return 0;
}
