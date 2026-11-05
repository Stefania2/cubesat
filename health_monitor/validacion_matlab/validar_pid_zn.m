% VALIDAR_PID_ZN  Validacion independiente de health_monitor/pid_reference.py
%
% Recalcula con Control System Toolbox la ganancia ultima, la sintonia de
% Ziegler-Nichols y la respuesta al escalon del lazo muestreado (planta con
% ZOH, controlador por Tustin, filtro derivativo N = 10) para G1 y G2, y
% escribe resultados_simulacion/hmta_pid_matlab.json.
% tests/test_health_monitor.py compara ese JSON con la implementacion numpy.
%
% Uso, desde la raiz del repositorio:
%   matlab -batch "run('health_monitor/validacion_matlab/validar_pid_zn.m')"

Ts = 0.01;
N = 10;
horizonte = 20;
s = tf('s');
plantas = struct('nombre', {'G1', 'G2'}, ...
                 'G', {8 / (s + 2)^3, 4 / (s * (s^2 + 13.5 * s + 38.048))});
controladores = {'P', 'PI', 'PID'};

raiz = fileparts(fileparts(fileparts(mfilename('fullpath'))));
salida = struct('herramienta', ['MATLAB ' version], 'Ts', Ts, 'N', N, ...
                'discretizacion', 'planta c2d zoh, controlador c2d tustin', ...
                'modelos', []);
modelos = [];
for p = plantas
    [Gm, ~, Wcg, ~] = margin(p.G);           % Gm = Ku (ganancia, no dB); Wcg = wu
    Ku = Gm;
    Pu = 2 * pi / Wcg;
    filas = [];
    for k = 1:numel(controladores)
        c = controladores{k};
        switch c
            case 'P'
                Kp = 0.5 * Ku; Ti = NaN; Td = NaN; C = pid(Kp);
            case 'PI'
                Kp = 0.45 * Ku; Ti = Pu / 1.2; Td = NaN; C = pid(Kp, Kp / Ti);
            case 'PID'
                Kp = 0.6 * Ku; Ti = Pu / 2; Td = Pu / 8;
                C = pid(Kp, Kp / Ti, Kp * Td, Td / N);
        end
        Gd = c2d(p.G, Ts, 'zoh');
        Cd = c2d(tf(C), Ts, 'tustin');
        T = feedback(Cd * Gd, 1);
        t = (0:Ts:horizonte)';
        y = step(T, t);
        info = stepinfo(T, 'SettlingTimeThreshold', 0.02, 'RiseTimeLimits', [0.1 0.9]);
        polos = pole(T);
        fila = struct('controlador', c, 'Kp', Kp, 'Ti', Ti, 'Td', Td, ...
                      'sobrepaso_pct', info.Overshoot, 'tiempo_subida_s', info.RiseTime, ...
                      'tiempo_asentamiento_s', info.SettlingTime, ...
                      'valor_final', dcgain(T), ...
                      'max_modulo_polo_z', max(abs(polos)), ...
                      'estable_discreto', isstable(T), ...
                      'y_muestras', y(1:100:end)');
        filas = [filas, fila]; %#ok<AGROW>
    end
    modelos = [modelos, struct('planta', p.nombre, 'Ku', Ku, 'wu', Wcg, 'Pu', Pu, ...
                               'controladores', filas)]; %#ok<AGROW>
end
salida.modelos = modelos;
ruta = fullfile(raiz, 'resultados_simulacion', 'hmta_pid_matlab.json');
fid = fopen(ruta, 'w');
fprintf(fid, '%s', jsonencode(salida, 'PrettyPrint', true));
fclose(fid);
fprintf('Escrito %s\n', ruta);
