#include "srsran/adt/byte_buffer.h"
#include "srsran/asn1/ngap/ngap_ies.h"
#include "srsran/asn1/xnap/common.h"
#include "srsran/asn1/xnap/xnap.h"
#include "srsran/asn1/xnap/xnap_ies.h"
#include "srsran/asn1/xnap/xnap_pdu_contents.h"
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

using namespace asn1;
using namespace asn1::xnap;
using namespace srsran;

static std::string hex_string(const byte_buffer& buffer)
{
  std::ostringstream stream;
  for (uint8_t octet : buffer) {
    stream << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(octet);
  }
  return stream.str();
}

static void print_pdu(const char* name, xn_ap_pdu_c& pdu)
{
  byte_buffer buffer;
  bit_ref     writer(buffer);
  if (pdu.pack(writer) != SRSASN_SUCCESS) {
    std::cerr << name << ": pack failed\n";
    std::exit(2);
  }
  cbit_ref    reader(buffer);
  xn_ap_pdu_c decoded;
  if (decoded.unpack(reader) != SRSASN_SUCCESS) {
    std::cerr << name << ": unpack failed\n";
    std::exit(3);
  }
  std::cout << name << " " << hex_string(buffer) << "\n";
}

static std::string make_last_visited_ngran_cell()
{
  asn1::ngap::last_visited_ngran_cell_info_s info;
  auto&                                      cgi = info.global_cell_id.set_nr_cgi();
  cgi.plmn_id.from_string("00f110");
  cgi.nr_cell_id.from_number(0x66c0000);
  info.cell_type.cell_size.value = asn1::ngap::cell_size_opts::small;
  info.time_ue_stayed_in_cell    = 1;
  byte_buffer buffer;
  bit_ref     writer(buffer);
  if (info.pack(writer) != SRSASN_SUCCESS) {
    std::cerr << "LastVisitedNGRANCellInformation: pack failed\n";
    std::exit(4);
  }
  return hex_string(buffer);
}

static void set_basic_qos(qos_flow_level_qos_params_s& qos)
{
  qos.qos_characteristics.set_non_dyn().five_qi = 9;
  qos.alloc_and_retention_prio.prio_level       = 1;
  qos.alloc_and_retention_prio.pre_emption_cap.value =
      allocand_retention_prio_s::pre_emption_cap_opts::shall_not_trigger_preemption;
  qos.alloc_and_retention_prio.pre_emption_vulnerability.value =
      allocand_retention_prio_s::pre_emption_vulnerability_opts::not_preemptable;
}

static xn_ap_pdu_c make_request()
{
  xn_ap_pdu_c pdu;
  auto&       init = pdu.set_init_msg();
  init.load_info_obj(ASN1_XNAP_ID_HO_PREP);
  auto& request = init.value.ho_request();

  request->source_ng_ra_nnode_ue_xn_ap_id = 1;
  request->cause.set_radio_network() = cause_radio_network_layer_opts::ho_desirable_for_radio_reasons;
  auto& target = request->target_cell_global_id.set_nr();
  target.plmn_id.from_string("00f110");
  target.nr_ci.from_number(0x66c0000);
  request->guami.plmn_id.from_string("00f110");
  request->guami.amf_region_id.from_number(2);
  request->guami.amf_set_id.from_number(1);
  request->guami.amf_pointer.from_number(0);

  auto& context       = request->ue_context_info_ho_request;
  context.ng_c_ue_ref = 1;
  context.cp_tnl_info_source.set_endpoint_ip_address().from_string("00001010001101010000000100000100");
  context.ue_security_cap.nr_encyption_algorithms.from_number(0xc000);
  context.ue_security_cap.nr_integrity_protection_algorithms.from_number(0xc000);
  context.ue_security_cap.e_utra_encyption_algorithms.from_number(0);
  context.ue_security_cap.e_utra_integrity_protection_algorithms.from_number(0);
  context.security_info.key_ng_ran_star.from_number(1);
  context.security_info.ncc    = 0;
  context.ue_ambr.dl_ue_ambr   = 1000000000;
  context.ue_ambr.ul_ue_ambr   = 1000000000;

  pdu_session_res_to_be_setup_item_s session;
  session.pdu_session_id = 1;
  session.s_nssai.sst.from_number(1);
  auto& tunnel = session.ul_ng_u_tnl_at_up_f.set_gtp_tunnel();
  tunnel.tnl_address.from_string("00001010001101010000000100000011");
  tunnel.gtp_teid.from_string("00000001");
  session.pdu_session_type.value = pdu_session_type_opts::ipv4;
  qos_flows_to_be_setup_item_s flow;
  flow.qfi = 1;
  set_basic_qos(flow.qos_flow_level_qos_params);
  session.qos_flows_to_be_setup_list.push_back(flow);
  context.pdu_session_res_to_be_setup_list.push_back(session);
  context.rrc_context.from_string("00");

  last_visited_cell_item_c history;
  history.set_ng_ran_cell().from_string(make_last_visited_ngran_cell());
  request->ue_history_info.push_back(history);
  return pdu;
}

static xn_ap_pdu_c make_ack()
{
  xn_ap_pdu_c pdu;
  auto&       outcome = pdu.set_successful_outcome();
  outcome.load_info_obj(ASN1_XNAP_ID_HO_PREP);
  auto& ack = outcome.value.ho_request_ack();

  ack->source_ng_ra_nnode_ue_xn_ap_id = 1;
  ack->target_ng_ra_nnode_ue_xn_ap_id = 2;
  pdu_session_res_admitted_item_s session;
  session.pdu_session_id = 1;
  qos_flows_admitted_item_s flow;
  flow.qfi = 1;
  session.pdu_session_res_admitted_info.qos_flows_admitted_list.push_back(flow);
  ack->pdu_session_res_admitted_list.push_back(session);
  ack->target2_source_ng_ra_nnode_transp_container.from_string("00");
  return pdu;
}

int main()
{
  auto request = make_request();
  print_pdu("HandoverRequest", request);
  auto acknowledge = make_ack();
  print_pdu("HandoverRequestAcknowledge", acknowledge);
  return 0;
}
