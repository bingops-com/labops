CREATE OR REPLACE FUNCTION identity.merge_progress(first_state jsonb,other_state jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $$
DECLARE result jsonb:=coalesce(other_state,'{}')||coalesce(first_state,'{}'); key text; merged jsonb;
BEGIN
 FOREACH key IN ARRAY ARRAY['done','review','onboarding','favorites','checklist'] LOOP
  SELECT coalesce(jsonb_agg(value ORDER BY value),'[]') INTO merged FROM (
   SELECT DISTINCT value FROM jsonb_array_elements(coalesce(first_state->key,'[]')||coalesce(other_state->key,'[]'))
  ) values;
  result:=jsonb_set(result,ARRAY[key],merged);
 END LOOP;
 result:=jsonb_set(result,'{notes}',coalesce(other_state->'notes','{}')||coalesce(first_state->'notes','{}'));
 result:=jsonb_set(result,'{training}',coalesce(other_state->'training','{}')||coalesce(first_state->'training','{}'));
 SELECT coalesce(jsonb_agg(value ORDER BY value->>'date'),'[]') INTO merged FROM (
  SELECT DISTINCT value FROM jsonb_array_elements(coalesce(first_state#>'{training,attempts}','[]')||coalesce(other_state#>'{training,attempts}','[]'))
 ) attempts;
 result:=jsonb_set(result,'{training,attempts}',merged);
 SELECT coalesce(jsonb_agg(value ORDER BY value->>'date'),'[]') INTO merged FROM (
  SELECT DISTINCT ON(value->>'key') value FROM jsonb_array_elements(coalesce(first_state->'experience','[]')||coalesce(other_state->'experience','[]'))
  ORDER BY value->>'key',(value->>'xp')::numeric DESC,value->>'date' DESC
 ) awards;
 result:=jsonb_set(result,'{experience}',merged);
 SELECT coalesce(jsonb_agg(value ORDER BY value->>'date'),'[]') INTO merged FROM (
  SELECT DISTINCT ON(value->>'id') value FROM jsonb_array_elements(coalesce(first_state->'exams','[]')||coalesce(other_state->'exams','[]'))
  ORDER BY value->>'id',value->>'date' DESC
 ) exams;
 RETURN jsonb_set(result,'{exams}',merged);
END $$;
REVOKE ALL ON FUNCTION identity.merge_progress(jsonb,jsonb) FROM PUBLIC;
