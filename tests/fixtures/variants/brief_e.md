# Harbour Mutual: material for the payment-reminder voice assistant

Harbour Mutual is fictional. Every customer, debt and payment here is synthetic. (Uydurma prova brief'i; hiçbir değeri `src/` altına girmez.)

---

## 1. Email thread

**From:** Operations lead, Customer Finance
**To:** Assistant project
**Subject:** RE: RE: go-live checklist for the reminder assistant

> Quick recap from Tuesday so nobody has to dig through the thread.

The assistant rings members who are behind on a personal loan, a credit card or a car loan, anywhere from 1 to 50 days. On every call we already know `customer_id` (send it to every system), `first_name`, `last_name`, `title` and `now` (the moment of the call; use it for all date maths, never the actual clock).

Opening line, word for word: "Hi, you're speaking with Harbour Mutual's virtual assistant, and this call is being recorded." After that, ask "Could I check I'm speaking with {title} {last_name}?". We only accept a plain yes, "speaking", "it's me", or the member saying their own name. If it is still not clear after we have asked twice, wrap up as no_contact with reason unclear.

Absolutely nothing about money, products or arrears before the member has passed the security checks, whoever answers.

Someone else answers? Don't explain the call. Ask when the member is free. Callback slots: Monday to Thursday between 08:30 and 18:00, Friday only between 08:30 and 13:00, never on weekends or holidays, and only on the next business day (not today). If they can only give a time that doesn't fit, ask one more time; still no good means no booking. Wrong number and death of the member have their own codes. For a death, say "I'm very sorry to hear that." and nothing more.

Security is three questions, one at a time, in this order: date of birth, then the first line of the home address (just the house number is enough), then the last four digits of the phone number on file. Two wrong answers in total are tolerated; a third wrong answer fails the check. If the member refuses, explain once that the questions keep their account safe; if they refuse again, end the call (security declined).

Thanks,
Ops

---

## 2. Collections policy, part 3 (extract)

3.1 Bank holidays (no business day): the Monday after Easter does not apply this year; observe 2026-11-02 (All Souls, regional), 2026-12-08, 2026-12-25 and 2026-12-28. Business days are Monday to Friday except these.

3.2 After security passes, call `get_account`. Tell the member we're calling about an overdue payment, name the product ("credit card ending" plus the last four digits, "personal loan" or "car loan"), the overdue amount and how many days overdue it is.

3.3 Latest arrangement date:

- 1 to 9 days overdue (stage A): 11th business day after today, 1 persuasion attempt.
- 10 to 29 days overdue (stage B): 6th business day after today, 2 persuasion attempts.
- 30 to 50 days overdue (stage C): 4th business day after today, 2 persuasion attempts.

3.4 Ask for the full overdue amount first ("Could you settle the full amount today?"). The lowest amount we can accept is `minimum_payment` for credit cards and `instalment_amount` for loans. If the member says the full amount is too much, offer the lowest amount once and mention that the remainder stays overdue.

3.5 Persuasion: attempt 1 is the full amount on the last business day of this week (of next week if today is already that day). Attempt 2 (stages B and C) is the lowest amount on the latest arrangement date.

3.6 Read the product, amount and date back and ask "Is that right?". Record only after a clear yes. After a recorded arrangement say: "You'll get an SMS confirming this arrangement." If recording fails, try once more; if it fails again, apologise and end the call (system error).

3.7 Hardship (illness, bereavement, job loss): one line of sympathy, no persuasion, offer the support team. Yes: transfer to queue `support`. No: no arrangement, hardship.

3.8 Requests for a new plan or lower instalments: transfer to queue `restructuring`. A request for a person: ask once if we can help, then queue `general`.

3.9 "Already paid": say payments can take up to three business days to show, take nothing, end as paid. "Not my debt": don't argue, no arrangement, disputed.

3.10 Never offer discounts, payment holidays, fee waivers or new plans.

---

## 3. Memo: Risk & Compliance (applies from receipt; overrides the policy where different)

a) Stage B now runs from 10 to **34** days overdue and stage C from **35** to 50.
b) Add 2026-11-11 as a holiday for our call centre (staff day).
c) The dialler team renamed one code: what used to be `no_arrangement / declined` is now `no_arrangement / refused`. Use the new name everywhere.
d) Until 2026-11-30 inclusive, stage A members get the 9th business day (not the 11th) as the latest arrangement date. From 2026-12-01 the policy value applies again.

---

## 4. Dialler result codes (export from the dialler config)

```
RESULT            REASONS
arranged          -
paid              -
transferred       new_plan | person | support
no_arrangement    declined | hardship | disputed | system_error
security_failed   wrong_answers | declined
no_contact        callback | no_callback | wrong_number | deceased | unclear
```

Mapping notes from the dialler team: `transferred/new_plan` is the restructuring queue, `transferred/person` the general queue, `transferred/support` the support queue.
