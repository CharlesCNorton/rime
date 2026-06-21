1. Implement coprime ring lengths per channel (5, 7, 9, 11, 13, 17, 19, 23) — all 8 rings currently use RING_STAGES=5, contradicting the comment on line 10 claiming coprime lengths 5-29
2. Fix comment on line 10 to match actual implementation until coprime lengths are implemented
3. Integrate ECP5 DTR primitive for direct die temperature readout in health reports
4. Extend path agreement monitor to check all 8 channels, not just channel 0 as representative
5. Document the relationship between gen_lpf.py, gen_lpf_constraints.py, place_ember.py, and the committed ember_placement.lpf — which is source of truth
6. Add README meeting the experiment documentation standard (methodology, results, interpretation, resource usage, reproducing instructions)
7. Commit raw UART capture as primary evidence
8. Add parse_results.py that reproduces analysis from raw capture
9. Run NIST SP 800-22 statistical test suite on captured output and commit results
10. Document actual measured ring frequencies and their thermal drift coefficients from warmup period data
11. Document and validate the sampling ratio (12.5 MHz sample clock vs measured ring frequency) to confirm sufficient jitter accumulation
12. Move from firmware/images/ to experiments/ or document why it lives in images/ despite not being a service image
13. Expand compressed variable names (scc, scd, tbc, hb, os, me_) for readability
14. Refactor the 30-case output state machine health report string builder to be less fragile when adding or removing fields
15. Add per-channel entropy quality tracking instead of using channel 0 as representative for autocorrelation and runs tests
