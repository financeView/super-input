import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

struct SuperInputRerankRequest: Encodable {
  let sessionID: String
  let requestID: Int
  let keys: String
  let preedit: String
  let candidates: [String]
  let context: String
  let trust: String

  enum CodingKeys: String, CodingKey {
    case sessionID = "session_id"
    case requestID = "request_id"
    case keys
    case preedit
    case candidates
    case context
    case trust
  }
}

struct SuperInputRerankResponse: Decodable {
  let mode: String
  let best: Int?
  let confidence: Double
  let order: [Int]
  let l2Text: String?

  enum CodingKeys: String, CodingKey {
    case mode
    case best
    case confidence
    case order
    case l2Text = "l2_text"
  }
}

/// Authenticated loopback-only client. Request text, candidates, and context are never logged.
final class SuperInputRerankClient {
  private let endpoint: URL
  private let tokenURL: URL
  private let session: URLSession

  init(port: Int? = nil, tokenPath: String? = nil) {
    let configuredPort = port ?? UserDefaults.standard.integer(forKey: "SuperInputPort")
    let effectivePort = (1...65_535).contains(configuredPort) ? configuredPort : 47_625
    endpoint = URL(string: "http://127.0.0.1:\(effectivePort)/rerank")!

    let configuredPath = tokenPath ?? UserDefaults.standard.string(forKey: "SuperInputTokenPath")
    let path = configuredPath ?? "~/Library/Application Support/super-input/token"
    tokenURL = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)

    let configuration = URLSessionConfiguration.ephemeral
    configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
    configuration.timeoutIntervalForRequest = 1.5
    configuration.timeoutIntervalForResource = 1.5
    session = URLSession(configuration: configuration)
  }

  @discardableResult
  func rerank(
    _ payload: SuperInputRerankRequest,
    completion: @escaping (Result<SuperInputRerankResponse, Error>) -> Void
  ) -> URLSessionDataTask? {
    guard let token = readPrivateToken() else { return nil }

    var request = URLRequest(url: endpoint)
    request.httpMethod = "POST"
    request.timeoutInterval = 1.5
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("1", forHTTPHeaderField: "X-SuperInput-Protocol")

    do {
      request.httpBody = try JSONEncoder().encode(payload)
    } catch {
      completion(.failure(error))
      return nil
    }

    let task = session.dataTask(with: request) { data, response, error in
      if let error {
        completion(.failure(error))
        return
      }
      guard let http = response as? HTTPURLResponse,
            (200..<300).contains(http.statusCode),
            let data else {
        completion(.failure(URLError(.badServerResponse)))
        return
      }
      do {
        completion(.success(try JSONDecoder().decode(SuperInputRerankResponse.self, from: data)))
      } catch {
        completion(.failure(error))
      }
    }
    task.resume()
    return task
  }

  private func readPrivateToken() -> String? {
    let descriptor = tokenURL.path.withCString { open($0, O_RDONLY | O_NOFOLLOW) }
    guard descriptor >= 0 else { return nil }
    defer { _ = close(descriptor) }

    var metadata = stat()
    guard fstat(descriptor, &metadata) == 0,
          (metadata.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          metadata.st_uid == uid_t(getuid()),
          (metadata.st_mode & 0o077) == 0 else { return nil }

    var bytes = [UInt8](repeating: 0, count: 256)
    let count = bytes.withUnsafeMutableBytes { buffer -> Int in
      guard let baseAddress = buffer.baseAddress else { return -1 }
      return read(descriptor, baseAddress, buffer.count)
    }
    guard count > 0, count < bytes.count else { return nil }
    let token = String(decoding: bytes.prefix(count), as: UTF8.self)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return token.count >= 32 ? token : nil
  }
}
