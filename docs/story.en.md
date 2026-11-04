# I just wanted to read a text on another device. QQ got a delivery job.

The idea was simple: see messages from one SIM on different devices without looking for the phone that held it. Then “move a message” grew into phone automation, authentication, a reverse proxy, a bot, dual-SIM detection and a surprisingly long discussion about failure.

## First, get a message through

An iPhone shortcut submits the sender, body, time and recipient to a FastAPI gateway. The gateway checks the Bearer token and recipient, then calls a local OneBot endpoint. NapCat delivers a plain-text message to the selected QQ group.

QQ has one job here: deliver the message. It does not need to understand how the message feels.

The server already hosted other services, so ports and proxy routes had to be checked first. The gateway listens on loopback, and the proxy exposes only the required routes. Bot identity and group membership also need checking: an available API does not prove the right people received a message.

The original iPhone deployment used public HTTP. It worked, but did not encrypt the message or token in transit. A working demo is not the same as a safe channel for sensitive messages. This public version recommends verified HTTPS; it does not claim the original link was encrypted.

## Dual SIM changed the question

The Android client had a harder problem before uploading anything: which SIM received the message?

The default data or voice SIM does not prove where an SMS arrived. The app checks subscription and slot evidence and asks for tests on both lines of a dual-SIM phone. Unknown, conflicting or non-shared lines are blocked. Only then does it parse the body, apply keyword rules and encrypt a queued message.

A SIM change, system update or vendor-specific implementation can change the evidence available. Code can express the rule; actual phones still need testing.

## Sent is not the same as received

A network timeout may happen before the server gets a request, or after QQ has sent the message but before the confirmation returns. To a client, both can look the same.

Android assigns a stable ID. The server durably accepts the message and delivers it in the background. It waits while QQ is known to be offline and expires old messages. Once a send has begun, an ambiguous result becomes `delivery_unknown` and is not automatically replayed. This avoids blind duplicates, at the cost of occasionally requiring a human to check the group.

The older iPhone endpoint does not have the same durable queue and deduplication guarantees. The two paths should not be described as equally reliable.

## From personal deployment to readable project

A real deployment contains server addresses, phone numbers, account IDs, certificates, tokens and private operational scripts. The public version leaves those out and takes server targets from environment variables. Its Android configuration trusts system CAs; operators must configure their own deployment and certificates.

This is a sanitized implementation reference, not a guarantee that every phone exposes reliable SIM metadata or keeps background tasks running. When a message crosses several systems, the useful question is not only how quickly it succeeds, but what we can actually know when it fails.
