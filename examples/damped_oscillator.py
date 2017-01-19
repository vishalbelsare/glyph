"""gp application."""

import logging
import argparse
from toolz import cons

import numpy
import scipy

from glyph import application
from glyph import gp
from glyph import control_problem
from glyph import assessment
from glyph import utils


# Setup of the control problem and gp algorithm.
class Individual(gp.AExpressionTree):
    """The gp representation (genotype) of the actuator for the control problem."""

    pset = gp.sympy_primitive_set(categories=['algebraic', 'trigonometric', 'exponential'],
                                  arguments=['y_0', 'y_1'], constants=['c'])


class AssessmentRunner(assessment.AAssessmentRunner):
    """Define a measure for the fitness assessment.

    Uses constant optimization. Optimal values for the constants are stored to
    an individual's popt attribute.
    """

    def setup(self):
        # Setup dynamic system.
        self.nperiods = 50.0
        self.x = numpy.linspace(0.0, self.nperiods * 2.0 * numpy.pi, 2000, dtype=numpy.float64)
        self.yinit = numpy.array([0.0, 1.0])
        self.params = dict(omega=1.0, c=3.0/8.0, k=0.0)
        # Target parameters.
        self.omega = 1.0
        self.ampl = 1.0
        self.NT = self.nperiods * 2.0 * numpy.pi / self.omega

    def measure(self, individual):
        popt, rmse_opt = assessment.const_opt_leastsq(self.rmse, individual)
        assert len(rmse_opt) == 2
        fitness = rmse_opt[0], rmse_opt[1], len(individual), popt
        return fitness

    def assign_fitness(self, individual, fitness):
        individual.fitness.values = fitness[:-1]
        individual.popt = fitness[-1]

    # TODO(jg): maybe as cached (beause of constant optimization).
    def rmse(self, individual, *f_args):
        y = self.trajectory(individual, *f_args)
        # 2/NT * ∫y0^2 dt from 0 to N*T.
        ampl_ = numpy.sqrt(scipy.trapz(y[0, :]**2, x=self.x) * 2.0 / self.NT)
        # 2/NTA^2 * ∫y1^2 dt from 0 to N*T.
        omega_ = numpy.sqrt(scipy.trapz(y[1, :]**2, x=self.x) * 2.0 / (self.NT * ampl_**2))
        rmse_ampl = utils.numeric.rmse(self.ampl, ampl_)
        rmse_omega = utils.numeric.rmse(self.omega, omega_)
        # Alternative measure.
        # rmse_ampl = utils.numeric.rmse(self.ampl * numpy.sin(self.omega * self.x), y[0, :])
        # rmse_omega = utils.numeric.rmse(self.ampl * self.omega * numpy.cos(self.omega * self.x), y[1, :])
        return assessment.replace_nan((rmse_ampl, rmse_omega))

    def trajectory(self, individual, *f_args):
        dy = control_problem.anharmonic_oscillator(gp.sympy_phenotype(individual), **self.params)
        return utils.numeric.integrate(dy, yinit=self.yinit, x=self.x, f_args=f_args)


def main():
    """Entry point of application."""
    program_description = 'Damped oscillator d²y/dt² = -k*y - c*dy/dt'
    parser = argparse.ArgumentParser(description=program_description)
    parser.add_argument('--params', type=utils.argparse.ntuple(2, float), default=(3.0/8.0, 1.0),
                        help='parameters c,k for the damped oscillator (default: 3/8,1)')
    parser.add_argument('--plot', help='plot best results', action='store_true')

    app, args = application.default_console_app(Individual, AssessmentRunner, parser=parser)
    app.assessment_runner.params['c'] = app.args.params[0]
    app.assessment_runner.params['k'] = app.args.params[1]
    app.run()

    logger = logging.getLogger(__name__)
    logger.info('\n')
    logger.info('Hall of Fame:')
    for individual in app.gp_runner.halloffame:
        popt = getattr(individual, 'popt', ())
        logger.info('{}  {}, {} = {}'.format(individual.fitness.values, str(individual), individual.pset.constants, popt))

    if not args.plot:
        return
    # Plot n best results.
    import matplotlib.pyplot as plt
    import seaborn
    n = 2
    seaborn.set_palette('husl', n + 2)
    alpha = 0.75
    label_size = 16
    title_size = 20
    assessment_runner = AssessmentRunner()
    params, yinit = assessment_runner.params, assessment_runner.yinit
    x, ampl, omega = assessment_runner.x, assessment_runner.ampl, assessment_runner.omega
    title = program_description + '\nparams={}, yinit={}'.format(params, yinit, fontsize=title_size)
    ax0 = plt.subplot2grid((2, 2), (0, 0))
    ax1 = plt.subplot2grid((2, 2), (1, 0))
    ax2 = plt.subplot2grid((2, 2), (1, 1))
    lines, labels = [], []
    target = (ampl * numpy.sin(omega * x), ampl * omega * numpy.cos(omega * x))
    l, = ax2.plot(target[0], target[1], linestyle='dotted', alpha=alpha)
    ax0.plot(x, target[0], linestyle='dotted', alpha=alpha, color=l.get_color())
    ax1.plot(x, target[1], linestyle='dotted', alpha=alpha, color=l.get_color())
    labels.append('target')
    lines.append(l)
    uncontrolled = Individual.from_string('Add(y_0, Neg(y_0))')
    for ind in cons(uncontrolled, reversed(app.gp_runner.halloffame[:n])):
        popt = getattr(ind, 'popt', numpy.zeros(len(ind.pset.constants)))
        label = 'with $a(y_0, y_1) = {}$, $c={}$'.format(str(ind), popt)
        label = label.replace('**', '^').replace('*', '\cdot ')
        y = assessment_runner.trajectory(ind, *popt)
        l, = ax0.plot(x, y[0, :], alpha=alpha)
        ax1.plot(x, y[1, :], alpha=alpha, color=l.get_color())
        ax2.plot(y[0, :], y[1, :], alpha=alpha, color=l.get_color())
        labels.append(label)
        lines.append(l)
    ax0.set_ylabel('$y_0$', fontsize=label_size)
    ax0.set_xlabel('time', fontsize=label_size)
    ax1.set_ylabel('$y_1$', fontsize=label_size)
    ax1.set_xlabel('time', fontsize=label_size)
    ax2.set_xlabel('$y_0$', fontsize=label_size)
    ax2.set_ylabel('$y_1$', fontsize=label_size)
    ax2.set_title('Phase Portrait', fontsize=label_size)
    plt.figlegend(lines, labels, loc='upper right', bbox_to_anchor=(0.9, 0.9), fontsize=label_size)
    plt.suptitle(title, fontsize=title_size)
    plt.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05)
    plt.show()


if __name__ == '__main__':
    main()
