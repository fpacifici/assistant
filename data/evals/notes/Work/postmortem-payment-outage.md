# Postmortem: payment outage of 12 March 2026

## Summary

Card payments failed for 47 minutes, from 09:12 to 09:59 CET. About 1,300 payments were declined and customers had to retry.

## Root cause

The TLS certificate of the payment gateway's internal endpoint expired at 09:12. It was issued by hand two years earlier and was not covered by the automatic renewal job.

## Timeline

- 09:12 first alerts on the payment error rate
- 09:31 on-call engineer finds the expired certificate
- 09:55 new certificate deployed
- 09:59 error rate back to normal

## Action items

- Move every certificate to automatic renewal (owner: Tomás, by end of March)
- Alert 30 days before any certificate expires
- Add the payment gateway to the weekly synthetic checks
