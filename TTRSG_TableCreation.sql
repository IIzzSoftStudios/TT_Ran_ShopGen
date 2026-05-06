--
-- PostgreSQL database dump
--

\restrict fJ04BpVpjA0EM5VfpTT21lm6RRnmntsGG8pMY1P3J8dZIMX9LjnkcQWbR6cvigC

-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: modifier_scope; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.modifier_scope AS ENUM (
    'global',
    'regional',
    'city',
    'shop',
    'item'
);


--
-- Name: sourcing_preference; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sourcing_preference AS ENUM (
    'regional',
    'global',
    'hybrid'
);


--
-- Name: target_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.target_type AS ENUM (
    'region',
    'city',
    'shop',
    'item'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cities (
    city_id integer NOT NULL,
    name character varying(100) NOT NULL,
    size character varying(50),
    population integer,
    region character varying(100),
    gm_profile_id integer NOT NULL
);


--
-- Name: cities_city_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cities_city_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cities_city_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cities_city_id_seq OWNED BY public.cities.city_id;


--
-- Name: demand_modifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.demand_modifiers (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    scope public.modifier_scope NOT NULL,
    effect_value double precision NOT NULL,
    start_date timestamp without time zone,
    end_date timestamp without time zone,
    is_active boolean,
    gm_profile_id integer NOT NULL
);


--
-- Name: demand_modifiers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.demand_modifiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: demand_modifiers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.demand_modifiers_id_seq OWNED BY public.demand_modifiers.id;


--
-- Name: global_markets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.global_markets (
    market_id integer NOT NULL,
    item_id integer NOT NULL,
    total_supply integer,
    total_demand integer,
    average_price double precision NOT NULL,
    last_updated timestamp without time zone,
    gm_profile_id integer NOT NULL
);


--
-- Name: global_markets_market_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.global_markets_market_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: global_markets_market_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.global_markets_market_id_seq OWNED BY public.global_markets.market_id;


--
-- Name: gm_profile; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gm_profile (
    id integer NOT NULL,
    user_id integer NOT NULL
);


--
-- Name: gm_profile_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gm_profile_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gm_profile_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gm_profile_id_seq OWNED BY public.gm_profile.id;


--
-- Name: items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.items (
    item_id integer NOT NULL,
    name character varying(100) NOT NULL,
    type character varying(50) NOT NULL,
    rarity character varying(50) NOT NULL,
    base_price integer NOT NULL,
    description text,
    range character varying(50),
    damage character varying(100),
    rate_of_fire integer,
    min_str character varying(10),
    notes text,
    gm_profile_id integer NOT NULL,
    preferred_regions json
);


--
-- Name: items_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.items_item_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: items_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.items_item_id_seq OWNED BY public.items.item_id;


--
-- Name: market_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_events (
    event_id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    trigger_type character varying(50) NOT NULL,
    city_id integer,
    region character varying(100),
    effect_json json NOT NULL,
    start_date timestamp without time zone NOT NULL,
    end_date timestamp without time zone,
    is_active boolean,
    gm_profile_id integer NOT NULL
);


--
-- Name: market_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.market_events_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: market_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.market_events_event_id_seq OWNED BY public.market_events.event_id;


--
-- Name: modifier_targets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.modifier_targets (
    id integer NOT NULL,
    modifier_id integer NOT NULL,
    entity_type public.target_type NOT NULL,
    entity_id integer NOT NULL,
    gm_profile_id integer NOT NULL
);


--
-- Name: modifier_targets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.modifier_targets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: modifier_targets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.modifier_targets_id_seq OWNED BY public.modifier_targets.id;


--
-- Name: player; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.player (
    id integer NOT NULL,
    user_id integer NOT NULL,
    gm_profile_id integer NOT NULL,
    currency integer
);


--
-- Name: player_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.player_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: player_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.player_id_seq OWNED BY public.player.id;


--
-- Name: player_inventory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.player_inventory (
    id integer NOT NULL,
    player_id integer NOT NULL,
    item_id integer NOT NULL,
    quantity integer
);


--
-- Name: player_inventory_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.player_inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: player_inventory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.player_inventory_id_seq OWNED BY public.player_inventory.id;


--
-- Name: player_investments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.player_investments (
    investment_id integer NOT NULL,
    player_id integer NOT NULL,
    shop_id integer NOT NULL,
    amount_invested double precision NOT NULL,
    stake_percentage double precision NOT NULL,
    income_yield double precision NOT NULL,
    last_payout timestamp without time zone NOT NULL,
    gm_profile_id integer NOT NULL
);


--
-- Name: player_investments_investment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.player_investments_investment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: player_investments_investment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.player_investments_investment_id_seq OWNED BY public.player_investments.investment_id;


--
-- Name: production_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.production_history (
    history_id integer NOT NULL,
    node_id integer NOT NULL,
    date timestamp without time zone NOT NULL,
    amount_produced double precision NOT NULL,
    quality double precision NOT NULL
);


--
-- Name: production_history_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.production_history_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: production_history_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.production_history_history_id_seq OWNED BY public.production_history.history_id;


--
-- Name: regional_markets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.regional_markets (
    market_id integer NOT NULL,
    city_id integer NOT NULL,
    item_id integer NOT NULL,
    total_supply integer,
    total_demand integer,
    average_price double precision NOT NULL,
    last_updated timestamp without time zone,
    gm_profile_id integer NOT NULL
);


--
-- Name: regional_markets_market_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.regional_markets_market_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: regional_markets_market_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.regional_markets_market_id_seq OWNED BY public.regional_markets.market_id;


--
-- Name: resource_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resource_nodes (
    node_id integer NOT NULL,
    name character varying(100) NOT NULL,
    type character varying(50) NOT NULL,
    production_rate double precision NOT NULL,
    quality double precision NOT NULL,
    city_id integer NOT NULL,
    owner_id integer,
    gm_profile_id integer NOT NULL
);


--
-- Name: resource_nodes_node_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resource_nodes_node_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resource_nodes_node_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resource_nodes_node_id_seq OWNED BY public.resource_nodes.node_id;


--
-- Name: resource_transforms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resource_transforms (
    transform_id integer NOT NULL,
    input_item_id integer NOT NULL,
    output_item_id integer NOT NULL,
    conversion_rate double precision NOT NULL,
    shop_type character varying(100) NOT NULL,
    gm_profile_id integer NOT NULL
);


--
-- Name: resource_transforms_transform_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resource_transforms_transform_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resource_transforms_transform_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resource_transforms_transform_id_seq OWNED BY public.resource_transforms.transform_id;


--
-- Name: shop_cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shop_cities (
    shop_id integer NOT NULL,
    city_id integer NOT NULL
);


--
-- Name: shop_inventory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shop_inventory (
    inventory_id integer NOT NULL,
    shop_id integer,
    item_id integer,
    stock integer,
    dynamic_price double precision NOT NULL,
    sourcing_preference public.sourcing_preference
);


--
-- Name: shop_inventory_inventory_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.shop_inventory_inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: shop_inventory_inventory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.shop_inventory_inventory_id_seq OWNED BY public.shop_inventory.inventory_id;


--
-- Name: shop_maintenance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shop_maintenance (
    maintenance_id integer NOT NULL,
    shop_id integer NOT NULL,
    daily_cost double precision NOT NULL,
    last_payment timestamp without time zone NOT NULL,
    gm_profile_id integer NOT NULL
);


--
-- Name: shop_maintenance_maintenance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.shop_maintenance_maintenance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: shop_maintenance_maintenance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.shop_maintenance_maintenance_id_seq OWNED BY public.shop_maintenance.maintenance_id;


--
-- Name: shops; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shops (
    shop_id integer NOT NULL,
    type character varying(100) NOT NULL,
    name character varying(100) NOT NULL,
    gm_profile_id integer NOT NULL,
    preferred_region character varying(100)
);


--
-- Name: shops_shop_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.shops_shop_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: shops_shop_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.shops_shop_id_seq OWNED BY public.shops.shop_id;


--
-- Name: sim_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sim_rules (
    rule_id integer NOT NULL,
    rule_type character varying(50) NOT NULL,
    target_type character varying(50) NOT NULL,
    function_type character varying(50) NOT NULL,
    condition_json json NOT NULL,
    gm_profile_id integer NOT NULL
);


--
-- Name: sim_rules_rule_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sim_rules_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sim_rules_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sim_rules_rule_id_seq OWNED BY public.sim_rules.rule_id;


--
-- Name: simulation_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.simulation_logs (
    log_id integer NOT NULL,
    tick_id integer NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    event_type character varying(50) NOT NULL,
    details json NOT NULL,
    gm_profile_id integer NOT NULL
);


--
-- Name: simulation_logs_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.simulation_logs_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: simulation_logs_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.simulation_logs_log_id_seq OWNED BY public.simulation_logs.log_id;


--
-- Name: simulation_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.simulation_state (
    state_id integer NOT NULL,
    current_tick integer NOT NULL,
    speed character varying(10) NOT NULL,
    last_tick_time timestamp without time zone NOT NULL,
    gm_profile_id integer NOT NULL,
    sim_clicks_day integer NOT NULL DEFAULT 0,
    sim_clicks_week integer NOT NULL DEFAULT 0,
    sim_clicks_month integer NOT NULL DEFAULT 0,
    sim_clicks_year integer NOT NULL DEFAULT 0,
    sim_clicks_pause integer NOT NULL DEFAULT 0
);


--
-- Name: simulation_state_state_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.simulation_state_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: simulation_state_state_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.simulation_state_state_id_seq OWNED BY public.simulation_state.state_id;


--
-- Name: user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."user" (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    password character varying(100) NOT NULL,
    role character varying(50) NOT NULL
);


--
-- Name: user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_id_seq OWNED BY public."user".id;


--
-- Name: cities city_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities ALTER COLUMN city_id SET DEFAULT nextval('public.cities_city_id_seq'::regclass);


--
-- Name: demand_modifiers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.demand_modifiers ALTER COLUMN id SET DEFAULT nextval('public.demand_modifiers_id_seq'::regclass);


--
-- Name: global_markets market_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_markets ALTER COLUMN market_id SET DEFAULT nextval('public.global_markets_market_id_seq'::regclass);


--
-- Name: gm_profile id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gm_profile ALTER COLUMN id SET DEFAULT nextval('public.gm_profile_id_seq'::regclass);


--
-- Name: items item_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items ALTER COLUMN item_id SET DEFAULT nextval('public.items_item_id_seq'::regclass);


--
-- Name: market_events event_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_events ALTER COLUMN event_id SET DEFAULT nextval('public.market_events_event_id_seq'::regclass);


--
-- Name: modifier_targets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modifier_targets ALTER COLUMN id SET DEFAULT nextval('public.modifier_targets_id_seq'::regclass);


--
-- Name: player id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player ALTER COLUMN id SET DEFAULT nextval('public.player_id_seq'::regclass);


--
-- Name: player_inventory id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_inventory ALTER COLUMN id SET DEFAULT nextval('public.player_inventory_id_seq'::regclass);


--
-- Name: player_investments investment_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_investments ALTER COLUMN investment_id SET DEFAULT nextval('public.player_investments_investment_id_seq'::regclass);


--
-- Name: production_history history_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_history ALTER COLUMN history_id SET DEFAULT nextval('public.production_history_history_id_seq'::regclass);


--
-- Name: regional_markets market_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regional_markets ALTER COLUMN market_id SET DEFAULT nextval('public.regional_markets_market_id_seq'::regclass);


--
-- Name: resource_nodes node_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_nodes ALTER COLUMN node_id SET DEFAULT nextval('public.resource_nodes_node_id_seq'::regclass);


--
-- Name: resource_transforms transform_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_transforms ALTER COLUMN transform_id SET DEFAULT nextval('public.resource_transforms_transform_id_seq'::regclass);


--
-- Name: shop_inventory inventory_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_inventory ALTER COLUMN inventory_id SET DEFAULT nextval('public.shop_inventory_inventory_id_seq'::regclass);


--
-- Name: shop_maintenance maintenance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_maintenance ALTER COLUMN maintenance_id SET DEFAULT nextval('public.shop_maintenance_maintenance_id_seq'::regclass);


--
-- Name: shops shop_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shops ALTER COLUMN shop_id SET DEFAULT nextval('public.shops_shop_id_seq'::regclass);


--
-- Name: sim_rules rule_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sim_rules ALTER COLUMN rule_id SET DEFAULT nextval('public.sim_rules_rule_id_seq'::regclass);


--
-- Name: simulation_logs log_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_logs ALTER COLUMN log_id SET DEFAULT nextval('public.simulation_logs_log_id_seq'::regclass);


--
-- Name: simulation_state state_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_state ALTER COLUMN state_id SET DEFAULT nextval('public.simulation_state_state_id_seq'::regclass);


--
-- Name: user id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user" ALTER COLUMN id SET DEFAULT nextval('public.user_id_seq'::regclass);


--
-- Name: cities cities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT cities_pkey PRIMARY KEY (city_id);


--
-- Name: demand_modifiers demand_modifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.demand_modifiers
    ADD CONSTRAINT demand_modifiers_pkey PRIMARY KEY (id);


--
-- Name: global_markets global_markets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_markets
    ADD CONSTRAINT global_markets_pkey PRIMARY KEY (market_id);


--
-- Name: gm_profile gm_profile_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gm_profile
    ADD CONSTRAINT gm_profile_pkey PRIMARY KEY (id);


--
-- Name: gm_profile gm_profile_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gm_profile
    ADD CONSTRAINT gm_profile_user_id_key UNIQUE (user_id);


--
-- Name: items items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_pkey PRIMARY KEY (item_id);


--
-- Name: market_events market_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_events
    ADD CONSTRAINT market_events_pkey PRIMARY KEY (event_id);


--
-- Name: modifier_targets modifier_targets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modifier_targets
    ADD CONSTRAINT modifier_targets_pkey PRIMARY KEY (id);


--
-- Name: player_inventory player_inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_inventory
    ADD CONSTRAINT player_inventory_pkey PRIMARY KEY (id);


--
-- Name: player_investments player_investments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_investments
    ADD CONSTRAINT player_investments_pkey PRIMARY KEY (investment_id);


--
-- Name: player player_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player
    ADD CONSTRAINT player_pkey PRIMARY KEY (id);


--
-- Name: player player_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player
    ADD CONSTRAINT player_user_id_key UNIQUE (user_id);


--
-- Name: production_history production_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_history
    ADD CONSTRAINT production_history_pkey PRIMARY KEY (history_id);


--
-- Name: regional_markets regional_markets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regional_markets
    ADD CONSTRAINT regional_markets_pkey PRIMARY KEY (market_id);


--
-- Name: resource_nodes resource_nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_nodes
    ADD CONSTRAINT resource_nodes_pkey PRIMARY KEY (node_id);


--
-- Name: resource_transforms resource_transforms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_transforms
    ADD CONSTRAINT resource_transforms_pkey PRIMARY KEY (transform_id);


--
-- Name: shop_cities shop_cities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_cities
    ADD CONSTRAINT shop_cities_pkey PRIMARY KEY (shop_id, city_id);


--
-- Name: shop_inventory shop_inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_inventory
    ADD CONSTRAINT shop_inventory_pkey PRIMARY KEY (inventory_id);


--
-- Name: shop_maintenance shop_maintenance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_maintenance
    ADD CONSTRAINT shop_maintenance_pkey PRIMARY KEY (maintenance_id);


--
-- Name: shops shops_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shops
    ADD CONSTRAINT shops_pkey PRIMARY KEY (shop_id);


--
-- Name: sim_rules sim_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sim_rules
    ADD CONSTRAINT sim_rules_pkey PRIMARY KEY (rule_id);


--
-- Name: simulation_logs simulation_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_logs
    ADD CONSTRAINT simulation_logs_pkey PRIMARY KEY (log_id);


--
-- Name: simulation_state simulation_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_state
    ADD CONSTRAINT simulation_state_pkey PRIMARY KEY (state_id);


--
-- Name: user user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);


--
-- Name: user user_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_username_key UNIQUE (username);


--
-- Name: ix_cities_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cities_name ON public.cities USING btree (name);


--
-- Name: ix_cities_region; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cities_region ON public.cities USING btree (region);


--
-- Name: ix_items_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_items_name ON public.items USING btree (name);


--
-- Name: cities cities_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT cities_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: demand_modifiers demand_modifiers_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.demand_modifiers
    ADD CONSTRAINT demand_modifiers_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: global_markets global_markets_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_markets
    ADD CONSTRAINT global_markets_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: global_markets global_markets_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_markets
    ADD CONSTRAINT global_markets_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(item_id);


--
-- Name: gm_profile gm_profile_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gm_profile
    ADD CONSTRAINT gm_profile_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: items items_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: market_events market_events_city_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_events
    ADD CONSTRAINT market_events_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.cities(city_id);


--
-- Name: market_events market_events_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_events
    ADD CONSTRAINT market_events_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: modifier_targets modifier_targets_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modifier_targets
    ADD CONSTRAINT modifier_targets_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: modifier_targets modifier_targets_modifier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modifier_targets
    ADD CONSTRAINT modifier_targets_modifier_id_fkey FOREIGN KEY (modifier_id) REFERENCES public.demand_modifiers(id);


--
-- Name: player player_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player
    ADD CONSTRAINT player_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: player_inventory player_inventory_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_inventory
    ADD CONSTRAINT player_inventory_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(item_id);


--
-- Name: player_inventory player_inventory_player_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_inventory
    ADD CONSTRAINT player_inventory_player_id_fkey FOREIGN KEY (player_id) REFERENCES public.player(id);


--
-- Name: player_investments player_investments_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_investments
    ADD CONSTRAINT player_investments_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: player_investments player_investments_player_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_investments
    ADD CONSTRAINT player_investments_player_id_fkey FOREIGN KEY (player_id) REFERENCES public.player(id);


--
-- Name: player_investments player_investments_shop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_investments
    ADD CONSTRAINT player_investments_shop_id_fkey FOREIGN KEY (shop_id) REFERENCES public.shops(shop_id);


--
-- Name: player player_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player
    ADD CONSTRAINT player_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: production_history production_history_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.production_history
    ADD CONSTRAINT production_history_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.resource_nodes(node_id);


--
-- Name: regional_markets regional_markets_city_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regional_markets
    ADD CONSTRAINT regional_markets_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.cities(city_id);


--
-- Name: regional_markets regional_markets_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regional_markets
    ADD CONSTRAINT regional_markets_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: regional_markets regional_markets_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regional_markets
    ADD CONSTRAINT regional_markets_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(item_id);


--
-- Name: resource_nodes resource_nodes_city_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_nodes
    ADD CONSTRAINT resource_nodes_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.cities(city_id);


--
-- Name: resource_nodes resource_nodes_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_nodes
    ADD CONSTRAINT resource_nodes_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: resource_nodes resource_nodes_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_nodes
    ADD CONSTRAINT resource_nodes_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.player(id);


--
-- Name: resource_transforms resource_transforms_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_transforms
    ADD CONSTRAINT resource_transforms_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: resource_transforms resource_transforms_input_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_transforms
    ADD CONSTRAINT resource_transforms_input_item_id_fkey FOREIGN KEY (input_item_id) REFERENCES public.items(item_id);


--
-- Name: resource_transforms resource_transforms_output_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_transforms
    ADD CONSTRAINT resource_transforms_output_item_id_fkey FOREIGN KEY (output_item_id) REFERENCES public.items(item_id);


--
-- Name: shop_cities shop_cities_city_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_cities
    ADD CONSTRAINT shop_cities_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.cities(city_id);


--
-- Name: shop_cities shop_cities_shop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_cities
    ADD CONSTRAINT shop_cities_shop_id_fkey FOREIGN KEY (shop_id) REFERENCES public.shops(shop_id);


--
-- Name: shop_inventory shop_inventory_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_inventory
    ADD CONSTRAINT shop_inventory_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.items(item_id);


--
-- Name: shop_inventory shop_inventory_shop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_inventory
    ADD CONSTRAINT shop_inventory_shop_id_fkey FOREIGN KEY (shop_id) REFERENCES public.shops(shop_id);


--
-- Name: shop_maintenance shop_maintenance_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_maintenance
    ADD CONSTRAINT shop_maintenance_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: shop_maintenance shop_maintenance_shop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_maintenance
    ADD CONSTRAINT shop_maintenance_shop_id_fkey FOREIGN KEY (shop_id) REFERENCES public.shops(shop_id);


--
-- Name: shops shops_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shops
    ADD CONSTRAINT shops_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: sim_rules sim_rules_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sim_rules
    ADD CONSTRAINT sim_rules_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: simulation_logs simulation_logs_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_logs
    ADD CONSTRAINT simulation_logs_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- Name: simulation_state simulation_state_gm_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_state
    ADD CONSTRAINT simulation_state_gm_profile_id_fkey FOREIGN KEY (gm_profile_id) REFERENCES public.gm_profile(id);


--
-- PostgreSQL database dump complete
--

\unrestrict fJ04BpVpjA0EM5VfpTT21lm6RRnmntsGG8pMY1P3J8dZIMX9LjnkcQWbR6cvigC

