#include "srsran/adt/byte_buffer.h"
#include "srsran/asn1/e1ap/e1ap.h"
#include "srsran/asn1/e1ap/e1ap_pdu_contents.h"
#include "srsran/asn1/f1ap/common.h"
#include "srsran/asn1/f1ap/f1ap.h"
#include "srsran/asn1/f1ap/f1ap_pdu_contents.h"
#include <arpa/inet.h>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <netinet/sctp.h>
#include <poll.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <unistd.h>
#include <vector>

using namespace asn1;
using namespace srsran;

static std::string hex_string(const byte_buffer& buffer)
{
  std::ostringstream stream;
  for (uint8_t octet : buffer) {
    stream << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(octet);
  }
  return stream.str();
}

static std::string hex_string(const std::vector<uint8_t>& buffer)
{
  std::ostringstream stream;
  for (uint8_t octet : buffer) {
    stream << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(octet);
  }
  return stream.str();
}

template <typename Pdu>
static byte_buffer pack(Pdu& pdu)
{
  byte_buffer buffer;
  bit_ref     writer(buffer);
  if (pdu.pack(writer) != SRSASN_SUCCESS) {
    std::cerr << "APER pack failed\n";
    std::exit(20);
  }
  cbit_ref verify_reader(buffer);
  Pdu      verified;
  if (verified.unpack(verify_reader) != SRSASN_SUCCESS) {
    std::cerr << "APER verification decode failed\n";
    std::exit(21);
  }
  return buffer;
}

static int connect_peer(uint16_t port)
{
  int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_SCTP);
  if (fd < 0) {
    perror("socket");
    std::exit(22);
  }
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_port   = htons(port);
  inet_pton(AF_INET, "10.53.1.4", &address.sin_addr);
  if (connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
    perror("connect");
    std::exit(23);
  }
  return fd;
}

static std::vector<uint8_t> receive_response(int fd)
{
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(6);
  while (std::chrono::steady_clock::now() < deadline) {
    pollfd poll_fd{fd, POLLIN, 0};
    int    ready = poll(&poll_fd, 1, 500);
    if (ready <= 0 || (poll_fd.revents & POLLIN) == 0) {
      continue;
    }
    std::vector<uint8_t> buffer(65535);
    sockaddr_in          from{};
    socklen_t            from_len = sizeof(from);
    sctp_sndrcvinfo      info{};
    int                  flags = 0;
    int size = sctp_recvmsg(fd,
                            buffer.data(),
                            buffer.size(),
                            reinterpret_cast<sockaddr*>(&from),
                            &from_len,
                            &info,
                            &flags);
    if (size <= 0) {
      return {};
    }
    if ((flags & MSG_NOTIFICATION) != 0) {
      continue;
    }
    buffer.resize(static_cast<size_t>(size));
    return buffer;
  }
  return {};
}

static std::pair<int, std::string> f1_response_info(const std::vector<uint8_t>& bytes)
{
  if (bytes.empty()) {
    return {-1, "none"};
  }
  auto                    buffer = byte_buffer::create(bytes).value();
  cbit_ref                reader(buffer);
  asn1::f1ap::f1ap_pdu_c pdu;
  if (pdu.unpack(reader) != SRSASN_SUCCESS) {
    return {-2, "decode_failed"};
  }
  int procedure = -1;
  if (pdu.type().value == asn1::f1ap::f1ap_pdu_c::types_opts::successful_outcome) {
    procedure = pdu.successful_outcome().proc_code;
  } else if (pdu.type().value == asn1::f1ap::f1ap_pdu_c::types_opts::unsuccessful_outcome) {
    procedure = pdu.unsuccessful_outcome().proc_code;
  } else if (pdu.type().value == asn1::f1ap::f1ap_pdu_c::types_opts::init_msg) {
    procedure = pdu.init_msg().proc_code;
  }
  return {procedure, pdu.type().to_string()};
}

static std::pair<int, std::string> e1_response_info(const std::vector<uint8_t>& bytes)
{
  if (bytes.empty()) {
    return {-1, "none"};
  }
  auto                    buffer = byte_buffer::create(bytes).value();
  cbit_ref                reader(buffer);
  asn1::e1ap::e1ap_pdu_c pdu;
  if (pdu.unpack(reader) != SRSASN_SUCCESS) {
    return {-2, "decode_failed"};
  }
  int procedure = -1;
  if (pdu.type().value == asn1::e1ap::e1ap_pdu_c::types_opts::successful_outcome) {
    procedure = pdu.successful_outcome().proc_code;
  } else if (pdu.type().value == asn1::e1ap::e1ap_pdu_c::types_opts::unsuccessful_outcome) {
    procedure = pdu.unsuccessful_outcome().proc_code;
  } else if (pdu.type().value == asn1::e1ap::e1ap_pdu_c::types_opts::init_msg) {
    procedure = pdu.init_msg().proc_code;
  }
  return {procedure, pdu.type().to_string()};
}

template <typename Pdu>
static void send_case(int fd, uint32_t ppid, const char* case_id, Pdu& pdu, bool f1)
{
  byte_buffer payload = pack(pdu);
  std::vector<uint8_t> payload_bytes{payload.begin(), payload.end()};
  auto        sent_at =
      std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
          .count();
  int sent = sctp_sendmsg(fd, payload_bytes.data(), payload_bytes.size(), nullptr, 0, htonl(ppid), 0, 0, 0, 0);
  if (sent != static_cast<int>(payload.length())) {
    perror("sctp_sendmsg");
    std::exit(24);
  }
  auto response = receive_response(fd);
  auto info     = f1 ? f1_response_info(response) : e1_response_info(response);
  std::cout << "{\"case_id\":\"" << case_id << "\",\"send_epoch_ms\":" << sent_at << ",\"payload_hex\":\""
            << hex_string(payload) << "\",\"response_hex\":\"" << hex_string(response)
            << "\",\"response_procedure_code\":" << info.first << ",\"response_outcome\":\"" << info.second
            << "\"}\n";
}

static asn1::f1ap::f1ap_pdu_c make_f1_setup()
{
  asn1::f1ap::f1ap_pdu_c pdu;
  pdu.set_init_msg();
  pdu.init_msg().load_info_obj(ASN1_F1AP_ID_F1_SETUP);
  auto& request                = pdu.init_msg().value.f1_setup_request();
  request->transaction_id      = 41;
  request->gnb_du_id           = 0x5c01;
  request->gnb_du_name_present = true;
  request->gnb_du_name.from_string("stage5c-peer-du");
  request->gnb_du_rrc_version.latest_rrc_version.from_number(1);
  request->gnb_du_served_cells_list_present = true;

  protocol_ie_single_container_s<asn1::f1ap::gnb_du_served_cells_item_ies_o> container;
  container.set_item(ASN1_F1AP_ID_GNB_DU_SERVED_CELLS_ITEM);
  auto& item = container.value().gnb_du_served_cells_item();
  item.served_cell_info.nr_cgi.plmn_id.from_string("00f110");
  item.served_cell_info.nr_cgi.nr_cell_id.from_number(0x66c0001);
  item.served_cell_info.nr_pci              = 2;
  item.served_cell_info.five_gs_tac_present = true;
  item.served_cell_info.five_gs_tac.from_number(7);
  asn1::f1ap::served_plmns_item_s plmn;
  plmn.plmn_id.from_string("00f110");
  item.served_cell_info.served_plmns.push_back(plmn);
  item.served_cell_info.nr_mode_info.set_tdd();
  item.served_cell_info.nr_mode_info.tdd().nr_freq_info.nr_arfcn = 626748;
  asn1::f1ap::freq_band_nr_item_s band;
  band.freq_band_ind_nr = 78;
  item.served_cell_info.nr_mode_info.tdd().nr_freq_info.freq_band_list_nr.push_back(band);
  item.served_cell_info.nr_mode_info.tdd().tx_bw.nr_scs.value = asn1::f1ap::nr_scs_opts::scs30;
  item.served_cell_info.nr_mode_info.tdd().tx_bw.nr_nrb.value = asn1::f1ap::nr_nrb_opts::nrb51;
  item.served_cell_info.meas_timing_cfg.from_string("30");
  item.gnb_du_sys_info_present = true;
  item.gnb_du_sys_info.mib_msg.from_string("01c586");
  item.gnb_du_sys_info.sib1_msg.from_string(
      "92002808241099000001000000000a4213407800008c98d6d8d7f616e0804000020107e28180008000088a0dc7008000088a0007141a22"
      "81c874cc00020000232d5c6b6c65462001ec4cc5fc9c0493946a98d4d1e99355c00a1aba010580ec024646f62180");
  request->gnb_du_served_cells_list.push_back(container);
  return pdu;
}

static asn1::f1ap::f1ap_pdu_c make_f1_cfg_update()
{
  asn1::f1ap::f1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_F1AP_ID_GNB_DU_CFG_UPD);
  auto& request              = pdu.init_msg().value.gnb_du_cfg_upd();
  request->transaction_id    = 42;
  request->gnb_du_id_present = true;
  request->gnb_du_id         = 0x5c01;
  return pdu;
}

static asn1::f1ap::f1ap_pdu_c make_f1_reset()
{
  asn1::f1ap::f1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_F1AP_ID_RESET);
  auto& request           = pdu.init_msg().value.reset();
  request->transaction_id = 43;
  request->cause.set_misc().value = asn1::f1ap::cause_misc_opts::unspecified;
  request->reset_type.set_f1_interface().value = asn1::f1ap::reset_all_opts::reset_all;
  return pdu;
}

static asn1::e1ap::e1ap_pdu_c make_e1_setup()
{
  asn1::e1ap::e1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_E1AP_ID_GNB_CU_UP_E1_SETUP);
  auto& request                   = pdu.init_msg().value.gnb_cu_up_e1_setup_request();
  request->transaction_id         = 51;
  request->gnb_cu_up_id           = 0x5c02;
  request->gnb_cu_up_name_present = true;
  request->gnb_cu_up_name.from_string("stage5c-peer-cu-up");
  request->cn_support.value = asn1::e1ap::cn_support_opts::c_5gc;
  asn1::e1ap::supported_plmns_item_s plmn;
  plmn.plmn_id.from_string("00f110");
  request->supported_plmns.push_back(plmn);
  return pdu;
}

static asn1::e1ap::e1ap_pdu_c make_e1_cfg_update()
{
  asn1::e1ap::e1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_E1AP_ID_GNB_CU_UP_CFG_UPD);
  auto& request           = pdu.init_msg().value.gnb_cu_up_cfg_upd();
  request->transaction_id = 52;
  request->gnb_cu_up_id   = 0x5c02;
  request->supported_plmns_present = true;
  asn1::e1ap::supported_plmns_item_s plmn;
  plmn.plmn_id.from_string("00f110");
  request->supported_plmns.push_back(plmn);
  return pdu;
}

static asn1::e1ap::e1ap_pdu_c make_e1_reset()
{
  asn1::e1ap::e1ap_pdu_c pdu;
  pdu.set_init_msg().load_info_obj(ASN1_E1AP_ID_RESET);
  auto& request           = pdu.init_msg().value.reset();
  request->transaction_id = 53;
  request->cause.set_misc().value = asn1::e1ap::cause_misc_opts::unspecified;
  request->reset_type.set_e1_interface();
  return pdu;
}

int main(int argc, char** argv)
{
  if (argc != 2 || (std::string(argv[1]) != "f1ap" && std::string(argv[1]) != "e1ap")) {
    std::cerr << "usage: protocol_peer_endpoint f1ap|e1ap\n";
    return 2;
  }
  if (std::string(argv[1]) == "f1ap") {
    int  fd     = connect_peer(38472);
    auto setup  = make_f1_setup();
    auto update = make_f1_cfg_update();
    auto reset  = make_f1_reset();
    send_case(fd, 62, "f1ap_generated_f1_setup_request", setup, true);
    send_case(fd, 62, "f1ap_generated_gnb_du_configuration_update", update, true);
    send_case(fd, 62, "f1ap_generated_reset", reset, true);
    close(fd);
  } else {
    int  fd     = connect_peer(38462);
    auto setup  = make_e1_setup();
    auto update = make_e1_cfg_update();
    auto reset  = make_e1_reset();
    send_case(fd, 64, "e1ap_generated_gnb_cu_up_e1_setup_request", setup, false);
    send_case(fd, 64, "e1ap_generated_gnb_cu_up_configuration_update", update, false);
    send_case(fd, 64, "e1ap_generated_reset", reset, false);
    close(fd);
  }
  return 0;
}
