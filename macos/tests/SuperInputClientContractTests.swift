import Foundation

@main
struct SuperInputClientContractTests {
  static func main() throws {
    let request = SuperInputRerankRequest(
      sessionID: "test-session",
      requestID: 7,
      keys: "nihao",
      preedit: "ni hao",
      candidates: ["你好", "拟好"],
      context: "刚刚提交的句子。",
      trust: "T0"
    )
    let encoded = try JSONEncoder().encode(request)
    let object = try JSONSerialization.jsonObject(with: encoded) as? [String: Any]
    precondition(object?["session_id"] as? String == "test-session")
    precondition(object?["request_id"] as? Int == 7)
    precondition(object?["keys"] as? String == "nihao")
    precondition(object?["candidates"] as? [String] == ["你好", "拟好"])
    precondition(object?["context"] as? String == "刚刚提交的句子。")
    precondition(object?["trust"] as? String == "T0")

    let firstRequest = SuperInputRerankRequest(
      sessionID: "new-session",
      requestID: 1,
      keys: "nihao",
      preedit: "ni hao",
      candidates: ["你好"],
      context: "",
      trust: "T0"
    )
    let firstEncoded = try JSONEncoder().encode(firstRequest)
    let firstObject = try JSONSerialization.jsonObject(with: firstEncoded) as? [String: Any]
    precondition(firstObject?["context"] as? String == "")

    let l1 = Data("""
      {"mode":"L1","best":1,"confidence":0.73,"order":[1,0],"l2_text":null}
      """.utf8)
    let l1Response = try JSONDecoder().decode(SuperInputRerankResponse.self, from: l1)
    precondition(l1Response.mode == "L1")
    precondition(l1Response.best == 1)
    precondition(l1Response.order == [1, 0])
    precondition(l1Response.l2Text == nil)

    let l2 = Data("""
      {"mode":"L2","best":0,"confidence":0.1,"order":[0,1],"l2_text":"你好。"}
      """.utf8)
    let l2Response = try JSONDecoder().decode(SuperInputRerankResponse.self, from: l2)
    precondition(l2Response.mode == "L2")
    precondition(l2Response.l2Text == "你好。")

    let fastpath = Data("""
      {"mode":"fastpath","best":null,"confidence":0.0,"order":[0,1],"l2_text":null}
      """.utf8)
    let fastpathResponse = try JSONDecoder().decode(SuperInputRerankResponse.self, from: fastpath)
    precondition(fastpathResponse.mode == "fastpath")
    precondition(fastpathResponse.best == nil)
    precondition(fastpathResponse.order == [0, 1])

    print("SuperInputClientContractTests: PASS")
  }
}
