def validate_findings(packet):
    if not isinstance(packet,dict) or not isinstance(packet.get("findings"),list) or not packet["findings"]:
        raise ValueError("findings required")
    for item in packet["findings"]:
        if not isinstance(item,dict) or not isinstance(item.get("claim"),str) or not item["claim"].strip():
            raise ValueError("a nonempty claim is required")
        sources=item.get("sources")
        if not isinstance(sources,list) or not sources or not all(isinstance(source,str) and source.strip() for source in sources):
            raise ValueError("claim and sources required")
    return True
