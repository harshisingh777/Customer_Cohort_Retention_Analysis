-- Marketing spend per channel per month, in the reporting currency at the spend date's rate.
select
  s.channel,
  date_trunc('month', s.date)::date as month,
  sum(
    s.spend_amount * case
      when upper(s.currency) = {{ reporting_currency() }} then 1.0
      else (
        select x.rate from {{ source('raw', 'fx_rates') }} x
        where x.base = upper(s.currency) and x.quote = {{ reporting_currency() }} and x.date <= s.date
        order by x.date desc limit 1
      )
    end
  )::numeric(16, 2) as spend
from {{ source('raw', 'marketing_spend') }} s
where s.date < {{ data_cutoff() }}
group by 1, 2
