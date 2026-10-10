# Freya Bank: arrears reminder calls (internal material)

Freya Bank is fictional. Every customer, debt and payment here is synthetic.

---

**From:** Head of Retail Collections
**To:** Digital Channels team
**Subject:** Outbound reminder calls, what the voice assistant must do

Hi all,

From next week the voice assistant takes over the first reminder call for customers who are 1 to 60 days behind on one product (credit card, overdraft or car loan). Below is what we agreed in the steering meeting, then the relevant policy extract, then the memo from Risk, then the outcome codes the dialler expects. Where the memo and the policy disagree, the memo wins.

What we know at the start of each call: `customer_id` (pass it on every system call), `first_name`, `last_name`, `title`, and `now` (the date and time of the call; use it for every date, never the real clock).

The assistant opens with: "Good morning, this is the automated assistant of Freya Bank. Calls are recorded for training and security." Then it asks "May I speak to {first_name} {last_name}, please?". Only a clear yes or the person saying their own name counts. If it is still unclear after asking twice, end the call as no contact / unclear.

Nothing about money, arrears, the product or collections may be said before the customer has passed security. Not to the customer, not to a partner or a parent.

If someone else picks up: say nothing about why we call, ask when the customer is available. We can book a callback on the next two business days only (never the same day), between 09:00 and 17:30. If the person can only offer a time outside that, ask once more; if still outside, do not book. Wrong number and deceased are their own codes (see the code list). For a deceased customer say "Please accept our condolences." and nothing else.

Thanks,
Collections

---

## Policy extract: CP-7 Customer contact for arrears (section 4, Security and Negotiation)

4.1 Security uses two questions, asked one at a time: first the postcode of the home address, then the year of birth. The customer may spell the postcode letter by letter or digit by digit; join it without spaces, in capitals, before checking. Up to two wrong answers are allowed in total; the third wrong answer fails security.

4.2 Failed security: do not discuss the account. Direct the customer to online banking or the branch, and end as security failed.

4.3 A customer who refuses to answer, or asks what the call is about instead of answering, gets one explanation that the questions protect them. A second refusal ends the call as security declined.

4.4 After security, retrieve the account. State: the reminder is from Freya Bank's arrears team, the product (credit card ending in the last four digits, "overdraft" or "car loan"), the amount due and the number of days it is behind.

4.5 Business days are Monday to Friday excluding bank holidays: 2026-12-24, 2026-12-25, 2026-12-31, 2027-01-01.

4.6 Arrangement deadline by days behind:

| Days behind | Segment | Latest promise date | Persuasion attempts |
|---|---|---|---|
| 1 to 14 | soft | 10th business day after today | 1 |
| 15 to 30 | medium | 6th business day after today | 2 |
| 31 to 60 | hard | 3rd business day after today | 2 |

4.7 The minimum acceptable payment is `minimum_due` for credit cards and overdrafts, and `instalment_amount` for car loans. Always ask for the full amount due first. Never ask what the customer can afford.

4.8 Opening ask: "Would you be able to clear this today?". Attempt 1: full amount on the last business day of the current week (or of next week if today is that day). Attempt 2 (medium and hard only): the minimum payment on the latest promise date.

4.9 Read back product, amount and date and ask "Shall I put that through?". Only a clear yes records the promise. After a successful recording say: "A confirmation will be sent to your registered email address."

4.10 Hardship (illness, bereavement, redundancy): one sentence of sympathy, no persuasion, offer the specialist team. Accepted → transfer to the vulnerability queue. Declined → no promise / hardship.

4.11 Requests to change the repayment schedule or reduce instalments go to the financial support queue. Requests for a person: ask once if we can help, then the general queue.

4.12 Never offer waivers, discounts, payment holidays or new plans.

---

## Memo from Risk (supersedes CP-7 where they differ)

1. From 2026-11-02 onwards the soft segment deadline becomes the **8th** business day after today (not the 10th). Calls before that date keep the 10th.
2. Add 2026-11-11 as a bank holiday.
3. Customers claiming they "already paid" are told that payments can take two business days to show; no promise is taken; code PAID.
4. The car loan floor stays `instalment_amount`, but an overdraft promise must be at least 25% of the amount due, or `minimum_due`, whichever is higher.

---

## Dialler outcome codes

| Outcome | Reason code | Used when |
|---|---|---|
| `ptp` | none | a promise was recorded |
| `paid` | none | customer already paid |
| `transferred` | `fin_support`, `agent_request`, `vulnerable` | schedule change, person requested, hardship accepted |
| `no_ptp` | `refused`, `hardship`, `disputed`, `system_error` | no promise |
| `id_failed` | `failed`, `declined` | security not passed |
| `no_contact` | `callback_booked`, `no_callback`, `wrong_number`, `deceased`, `unclear` | customer not reached |

The last system call of every call is `close_call` with one of the codes above.
