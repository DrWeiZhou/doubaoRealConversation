import gzip
import json

PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

PROTOCOL_VERSION_BITS = 4
HEADER_BITS = 4
MESSAGE_TYPE_BITS = 4
MESSAGE_TYPE_SPECIFIC_FLAGS_BITS = 4
MESSAGE_SERIALIZATION_BITS = 4
MESSAGE_COMPRESSION_BITS = 4
RESERVED_BITS = 8

# Message Type:
CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010

SERVER_FULL_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111

# Message Type Specific Flags
NO_SEQUENCE = 0b0000  # no check sequence
POS_SEQUENCE = 0b0001
NEG_SEQUENCE = 0b0010
NEG_SEQUENCE_1 = 0b0011

MSG_WITH_EVENT = 0b0100

# Message Serialization
NO_SERIALIZATION = 0b0000
JSON = 0b0001
THRIFT = 0b0011
CUSTOM_TYPE = 0b1111

# Message Compression
NO_COMPRESSION = 0b0000
GZIP = 0b0001
CUSTOM_COMPRESSION = 0b1111


def generate_header(
        version=PROTOCOL_VERSION,
        message_type=CLIENT_FULL_REQUEST,
        message_type_specific_flags=MSG_WITH_EVENT,
        serial_method=JSON,
        compression_type=GZIP,
        reserved_data=0x00,
        extension_header=bytes()
):
    """
    protocol_version(4 bits), header_size(4 bits),
    message_type(4 bits), message_type_specific_flags(4 bits)
    serialization_method(4 bits) message_compression(4 bits)
    reserved （8bits) 保留字段
    header_extensions 扩展头(大小等于 8 * 4 * (header_size - 1) )
    """
    header = bytearray()
    header_size = int(len(extension_header) / 4) + 1
    header.append((version << 4) | header_size)
    header.append((message_type << 4) | message_type_specific_flags)
    header.append((serial_method << 4) | compression_type)
    header.append(reserved_data)
    header.extend(extension_header)
    return header


def parse_response(res):
    """
    - header
        - (4bytes)header
        - (4bits)version(v1) + (4bits)header_size
        - (4bits)messageType + (4bits)messageTypeFlags
            -- 0001    CompleteClient | -- 0001 hasSequence
            -- 0010    audioonly      | -- 0010 isTailPacket
                                           | -- 0100 hasEvent
        - (4bits)payloadFormat + (4bits)compression
        - (8bits) reserve
    - payload
        - [optional 4 bytes] event
        - [optional] session ID
          -- (4 bytes)session ID len
          -- session ID data
        - (4 bytes)data len
        - data
    """
    if isinstance(res, str):
        return {}
    if len(res) < 4:
        return {'message_type': 'INVALID_RESPONSE', 'error': 'Response is too short'}

    protocol_version = res[0] >> 4
    header_size = res[0] & 0x0f
    message_type = res[1] >> 4
    message_type_specific_flags = res[1] & 0x0f
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0f
    reserved = res[3]
    header_extensions = res[4:header_size * 4]
    payload = res[header_size * 4:]
    result = {}
    payload_msg = None
    payload_size = 0
    start = 0
    if message_type == SERVER_FULL_RESPONSE or message_type == SERVER_ACK:
        result['message_type'] = 'SERVER_FULL_RESPONSE'
        if message_type == SERVER_ACK:
            result['message_type'] = 'SERVER_ACK'
        if message_type_specific_flags & NEG_SEQUENCE > 0:
            result['seq'] = int.from_bytes(payload[start:start+4], "big", signed=False)
            start += 4
        if message_type_specific_flags & MSG_WITH_EVENT > 0:
            result['event'] = int.from_bytes(payload[start:start+4], "big", signed=False)
            start += 4
        
        # Check if there's enough data for session_id_size
        if len(payload) < start + 4:
            result['error'] = "Incomplete payload for session_id size"
            return result

        session_id_size = int.from_bytes(payload[start:start+4], "big", signed=True)
        start += 4

        # Check if there's enough data for session_id
        if len(payload) < start + session_id_size:
            result['error'] = "Incomplete payload for session_id"
            return result

        session_id = payload[start:start+session_id_size]
        result['session_id'] = session_id.decode('utf-8', errors='ignore')
        start += session_id_size

        # Check if there's enough data for payload_size
        if len(payload) < start + 4:
            result['error'] = "Incomplete payload for payload_size"
            return result

        payload_size = int.from_bytes(payload[start:start+4], "big", signed=False)
        start += 4

        payload_msg = payload[start:]

    elif message_type == SERVER_ERROR_RESPONSE:
        result['message_type'] = 'SERVER_ERROR_RESPONSE'
        if len(payload) >= 4:
            code = int.from_bytes(payload[:4], "big", signed=False)
            result['code'] = code
        if len(payload) >= 8:
            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
            payload_msg = payload[8:]
        else:
            payload_msg = payload[4:]

    else:
        result['message_type'] = f'UNKNOWN ({message_type})'
        result['raw_payload'] = payload.hex()

    if payload_msg is None:
        return result
        
    try:
        if message_compression == GZIP:
            payload_msg = gzip.decompress(payload_msg)
        
        if serialization_method == JSON:
            payload_msg = json.loads(payload_msg.decode("utf-8"))
        elif serialization_method != NO_SERIALIZATION:
            payload_msg = payload_msg.decode("utf-8")
        
        result['payload_msg'] = payload_msg
        result['payload_size'] = payload_size if payload_size > 0 else len(payload_msg)

    except Exception as e:
        result['error'] = f"Payload processing error: {e}"
        result['raw_payload_on_error'] = payload_msg.hex() if isinstance(payload_msg, bytes) else payload_msg

    return result