#include "srsran/adt/byte_buffer.h"
#include "srsran/asn1/e1ap/e1ap.h"
#include "srsran/asn1/e1ap/e1ap_pdu_contents.h"
#include "srsran/asn1/f1ap/common.h"
#include "srsran/asn1/f1ap/f1ap.h"
#include "srsran/asn1/f1ap/f1ap_pdu_contents.h"
#include <arpa/inet.h>
#include <chrono>
#include <cctype>
#include <cstdlib>
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

struct pdu_info {
  int         procedure_code = -1;
  int         transaction_id = -1;
  std::string outcome        = "none";
  std::string message        = "none";
};

static std::vector<uint8_t> parse_hex(const std::string& value)
{
  if (value.empty() || value.size() % 2 != 0 || value.size() > 131070) {
    std::cerr << "payload hex must be non-empty, even length, and at most 65535 bytes\n";
    std::exit(2);
  }
  std::vector<uint8_t> bytes;
  bytes.reserve(value.size() / 2);
  for (size_t i = 0; i < value.size(); i += 2) {
    if (!std::isxdigit(static_cast<unsigned char>(value[i])) ||
        !std::isxdigit(static_cast<unsigned char>(value[i + 1]))) {
      std::cerr << "payload contains non-hex characters\n";
      std::exit(3);
    }
    bytes.push_back(static_cast<uint8_t>(std::stoul(value.substr(i, 2), nullptr, 16)));
  }
  return bytes;
}

static bool valid_case_id(const std::string& value)
{
  if (value.empty() || value.size() > 128) {
    return false;
  }
  for (char character : value) {
    if (!std::islower(static_cast<unsigned char>(character)) &&
        !std::isdigit(static_cast<unsigned char>(character)) && character != '_') {
      return false;
    }
  }
  return true;
}

static std::string hex_string(const std::vector<uint8_t>& buffer)
{
  std::ostringstream stream;
  for (uint8_t octet : buffer) {
    stream << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(octet);
  }
  return stream.str();
}

static int connect_peer(uint16_t port)
{
  int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_SCTP);
  if (fd < 0) {
    perror("socket");
    std::exit(4);
  }
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_port   = htons(port);
  inet_pton(AF_INET, "10.53.1.4", &address.sin_addr);
  if (connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
    perror("connect");
    std::exit(5);
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

static pdu_info decode_f1_request(const std::vector<uint8_t>& bytes)
{
  auto                    buffer = byte_buffer::create(bytes).value();
  cbit_ref                reader(buffer);
  asn1::f1ap::f1ap_pdu_c pdu;
  if (pdu.unpack(reader) != SRSASN_SUCCESS ||
      pdu.type().value != asn1::f1ap::f1ap_pdu_c::types_opts::init_msg) {
    std::cerr << "external F1AP payload is not a decodable initiating message\n";
    std::exit(6);
  }
  pdu_info info;
  info.procedure_code = pdu.init_msg().proc_code;
  info.outcome        = "initiatingMessage";
  switch (info.procedure_code) {
    case ASN1_F1AP_ID_F1_SETUP:
      info.transaction_id = pdu.init_msg().value.f1_setup_request()->transaction_id;
      info.message        = "F1SetupRequest";
      break;
    case ASN1_F1AP_ID_GNB_DU_CFG_UPD:
      info.transaction_id = pdu.init_msg().value.gnb_du_cfg_upd()->transaction_id;
      info.message        = "GNBDUConfigurationUpdate";
      break;
    case ASN1_F1AP_ID_RESET:
      info.transaction_id = pdu.init_msg().value.reset()->transaction_id;
      info.message        = "Reset";
      break;
    default:
      std::cerr << "unsupported external F1AP procedure\n";
      std::exit(7);
  }
  return info;
}

static pdu_info decode_e1_request(const std::vector<uint8_t>& bytes)
{
  auto                    buffer = byte_buffer::create(bytes).value();
  cbit_ref                reader(buffer);
  asn1::e1ap::e1ap_pdu_c pdu;
  if (pdu.unpack(reader) != SRSASN_SUCCESS ||
      pdu.type().value != asn1::e1ap::e1ap_pdu_c::types_opts::init_msg) {
    std::cerr << "external E1AP payload is not a decodable initiating message\n";
    std::exit(8);
  }
  pdu_info info;
  info.procedure_code = pdu.init_msg().proc_code;
  info.outcome        = "initiatingMessage";
  switch (info.procedure_code) {
    case ASN1_E1AP_ID_GNB_CU_UP_E1_SETUP:
      info.transaction_id = pdu.init_msg().value.gnb_cu_up_e1_setup_request()->transaction_id;
      info.message        = "GNB-CU-UP-E1SetupRequest";
      break;
    case ASN1_E1AP_ID_GNB_CU_UP_CFG_UPD:
      info.transaction_id = pdu.init_msg().value.gnb_cu_up_cfg_upd()->transaction_id;
      info.message        = "GNB-CU-UP-ConfigurationUpdate";
      break;
    case ASN1_E1AP_ID_RESET:
      info.transaction_id = pdu.init_msg().value.reset()->transaction_id;
      info.message        = "Reset";
      break;
    default:
      std::cerr << "unsupported external E1AP procedure\n";
      std::exit(9);
  }
  return info;
}

static pdu_info decode_f1_response(const std::vector<uint8_t>& bytes)
{
  if (bytes.empty()) {
    return {};
  }
  auto                    buffer = byte_buffer::create(bytes).value();
  cbit_ref                reader(buffer);
  asn1::f1ap::f1ap_pdu_c pdu;
  if (pdu.unpack(reader) != SRSASN_SUCCESS) {
    return {-2, -1, "decodeFailed", "decodeFailed"};
  }
  pdu_info info;
  if (pdu.type().value == asn1::f1ap::f1ap_pdu_c::types_opts::successful_outcome) {
    info.procedure_code = pdu.successful_outcome().proc_code;
    info.outcome        = "successfulOutcome";
    switch (info.procedure_code) {
      case ASN1_F1AP_ID_RESET:
        info.transaction_id = pdu.successful_outcome().value.reset_ack()->transaction_id;
        info.message        = "ResetAcknowledge";
        break;
      case ASN1_F1AP_ID_F1_SETUP:
        info.transaction_id = pdu.successful_outcome().value.f1_setup_resp()->transaction_id;
        info.message        = "F1SetupResponse";
        break;
      case ASN1_F1AP_ID_GNB_DU_CFG_UPD:
        info.transaction_id = pdu.successful_outcome().value.gnb_du_cfg_upd_ack()->transaction_id;
        info.message        = "GNBDUConfigurationUpdateAcknowledge";
        break;
    }
  } else if (pdu.type().value == asn1::f1ap::f1ap_pdu_c::types_opts::unsuccessful_outcome) {
    info.procedure_code = pdu.unsuccessful_outcome().proc_code;
    info.outcome        = "unsuccessfulOutcome";
    if (info.procedure_code == ASN1_F1AP_ID_F1_SETUP) {
      info.transaction_id = pdu.unsuccessful_outcome().value.f1_setup_fail()->transaction_id;
      info.message        = "F1SetupFailure";
    } else if (info.procedure_code == ASN1_F1AP_ID_GNB_DU_CFG_UPD) {
      info.transaction_id = pdu.unsuccessful_outcome().value.gnb_du_cfg_upd_fail()->transaction_id;
      info.message        = "GNBDUConfigurationUpdateFailure";
    }
  }
  return info;
}

static pdu_info decode_e1_response(const std::vector<uint8_t>& bytes)
{
  if (bytes.empty()) {
    return {};
  }
  auto                    buffer = byte_buffer::create(bytes).value();
  cbit_ref                reader(buffer);
  asn1::e1ap::e1ap_pdu_c pdu;
  if (pdu.unpack(reader) != SRSASN_SUCCESS) {
    return {-2, -1, "decodeFailed", "decodeFailed"};
  }
  pdu_info info;
  if (pdu.type().value == asn1::e1ap::e1ap_pdu_c::types_opts::successful_outcome) {
    info.procedure_code = pdu.successful_outcome().proc_code;
    info.outcome        = "successfulOutcome";
    switch (info.procedure_code) {
      case ASN1_E1AP_ID_RESET:
        info.transaction_id = pdu.successful_outcome().value.reset_ack()->transaction_id;
        info.message        = "ResetAcknowledge";
        break;
      case ASN1_E1AP_ID_GNB_CU_UP_E1_SETUP:
        info.transaction_id = pdu.successful_outcome().value.gnb_cu_up_e1_setup_resp()->transaction_id;
        info.message        = "GNB-CU-UP-E1SetupResponse";
        break;
      case ASN1_E1AP_ID_GNB_CU_UP_CFG_UPD:
        info.transaction_id = pdu.successful_outcome().value.gnb_cu_up_cfg_upd_ack()->transaction_id;
        info.message        = "GNB-CU-UP-ConfigurationUpdateAcknowledge";
        break;
    }
  } else if (pdu.type().value == asn1::e1ap::e1ap_pdu_c::types_opts::unsuccessful_outcome) {
    info.procedure_code = pdu.unsuccessful_outcome().proc_code;
    info.outcome        = "unsuccessfulOutcome";
    if (info.procedure_code == ASN1_E1AP_ID_GNB_CU_UP_E1_SETUP) {
      info.transaction_id = pdu.unsuccessful_outcome().value.gnb_cu_up_e1_setup_fail()->transaction_id;
      info.message        = "GNB-CU-UP-E1SetupFailure";
    } else if (info.procedure_code == ASN1_E1AP_ID_GNB_CU_UP_CFG_UPD) {
      info.transaction_id = pdu.unsuccessful_outcome().value.gnb_cu_up_cfg_upd_fail()->transaction_id;
      info.message        = "GNB-CU-UP-ConfigurationUpdateFailure";
    }
  }
  return info;
}

static void send_case(int fd, uint32_t ppid, const std::string& case_id, const std::vector<uint8_t>& payload, bool f1)
{
  pdu_info request = f1 ? decode_f1_request(payload) : decode_e1_request(payload);
  auto sent_at =
      std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
          .count();
  int sent = sctp_sendmsg(fd, payload.data(), payload.size(), nullptr, 0, htonl(ppid), 0, 0, 0, 0);
  if (sent != static_cast<int>(payload.size())) {
    perror("sctp_sendmsg");
    std::exit(10);
  }
  auto response      = receive_response(fd);
  auto response_info = f1 ? decode_f1_response(response) : decode_e1_response(response);
  std::cout << "{\"case_id\":\"" << case_id << "\",\"send_epoch_ms\":" << sent_at
            << ",\"payload_hex\":\"" << hex_string(payload) << "\",\"request_procedure_code\":"
            << request.procedure_code << ",\"request_transaction_id\":" << request.transaction_id
            << ",\"request_message\":\"" << request.message << "\",\"response_hex\":\"" << hex_string(response)
            << "\",\"response_procedure_code\":" << response_info.procedure_code
            << ",\"response_transaction_id\":" << response_info.transaction_id << ",\"response_outcome\":\""
            << response_info.outcome << "\",\"response_message\":\"" << response_info.message << "\"}\n";
}

int main(int argc, char** argv)
{
  if (argc < 4 || argc % 2 != 0 || (std::string(argv[1]) != "f1ap" && std::string(argv[1]) != "e1ap")) {
    std::cerr << "usage: protocol_peer_endpoint f1ap|e1ap CASE_ID PAYLOAD_HEX [CASE_ID PAYLOAD_HEX ...]\n";
    return 1;
  }
  bool     f1   = std::string(argv[1]) == "f1ap";
  int      fd   = connect_peer(f1 ? 38472 : 38462);
  uint32_t ppid = f1 ? 62 : 64;
  for (int i = 2; i < argc; i += 2) {
    std::string case_id = argv[i];
    if (!valid_case_id(case_id)) {
      std::cerr << "invalid case ID\n";
      return 11;
    }
    send_case(fd, ppid, case_id, parse_hex(argv[i + 1]), f1);
  }
  close(fd);
  return 0;
}
